"""Tests for redirect rule engine, cycle/loop detection, chain bounds, and open-redirects.

Requirement SEO-4.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.seo.models import RedirectRule, RedirectStatusCode
from apps.sites.models import Domain, Site
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole


@pytest.fixture
def redirect_setup(db: None) -> dict[str, object]:
    admin = User.objects.create_user(email="admin@redirect.com", password="SecurePassword123!")
    workspace = Workspace.objects.create(name="Redirect Org", slug="redirect-org")
    WorkspaceMembership.objects.create(workspace=workspace, user=admin, role=WorkspaceRole.ADMIN)

    site = Site.objects.create(
        workspace=workspace,
        name="Redirect Site",
        slug="redirect-site",
        allowed_origins=["https://cdn.partner.com"],
        is_active=True,
    )
    Domain.objects.create(
        site=site, hostname="redirect.portal.org", is_verified=True, is_primary=True
    )

    return {
        "admin": admin,
        "workspace": workspace,
        "site": site,
    }


@pytest.mark.django_db
def test_redirect_crud_success(redirect_setup: dict[str, object]) -> None:
    client = APIClient()
    admin = redirect_setup["admin"]
    workspace = redirect_setup["workspace"]
    site = redirect_setup["site"]
    assert isinstance(workspace, Workspace)
    assert isinstance(site, Site)

    client.force_authenticate(user=admin)
    list_url = reverse(
        "seo:redirect_rule_list_create", kwargs={"workspace_id": workspace.id, "site_id": site.id}
    )

    # 1. Create 301 Moved Permanently redirect
    resp = client.post(
        list_url,
        {
            "source_path": "/old-blog/post-1/",
            "target_url": "/articles/post-1",
            "status_code": RedirectStatusCode.MOVED_PERMANENTLY,
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED
    data = resp.json()
    rule_id = data["id"]
    assert data["source_path"] == "/old-blog/post-1"
    assert data["target_url"] == "/articles/post-1"
    assert data["status_code"] == 301

    # 2. List redirects
    list_resp = client.get(list_url)
    assert list_resp.status_code == status.HTTP_200_OK
    assert list_resp.json()["count"] == 1

    # 3. Retrieve detail
    detail_url = reverse(
        "seo:redirect_rule_detail",
        kwargs={"workspace_id": workspace.id, "site_id": site.id, "rule_id": rule_id},
    )
    detail_resp = client.get(detail_url)
    assert detail_resp.status_code == status.HTTP_200_OK
    assert detail_resp.json()["id"] == rule_id

    # 4. Delete redirect
    del_resp = client.delete(detail_url)
    assert del_resp.status_code == status.HTTP_204_NO_CONTENT
    assert not RedirectRule.objects.filter(id=rule_id).exists()


@pytest.mark.django_db
def test_redirect_loop_detection(redirect_setup: dict[str, object]) -> None:
    client = APIClient()
    admin = redirect_setup["admin"]
    workspace = redirect_setup["workspace"]
    site = redirect_setup["site"]
    assert isinstance(workspace, Workspace)
    assert isinstance(site, Site)

    client.force_authenticate(user=admin)
    list_url = reverse(
        "seo:redirect_rule_list_create", kwargs={"workspace_id": workspace.id, "site_id": site.id}
    )

    # 1. Self-redirect loop: /page-a -> /page-a rejected
    self_loop = client.post(
        list_url,
        {"source_path": "/page-a", "target_url": "/page-a"},
        format="json",
    )
    assert self_loop.status_code == status.HTTP_400_BAD_REQUEST
    assert "immediate loop" in str(self_loop.json())

    # 2. Create /page-a -> /page-b
    r1 = client.post(
        list_url,
        {"source_path": "/page-a", "target_url": "/page-b"},
        format="json",
    )
    assert r1.status_code == status.HTTP_201_CREATED

    # 3. Direct cycle: /page-b -> /page-a rejected
    direct_cycle = client.post(
        list_url,
        {"source_path": "/page-b", "target_url": "/page-a"},
        format="json",
    )
    assert direct_cycle.status_code == status.HTTP_400_BAD_REQUEST
    assert "Redirect loop detected" in str(direct_cycle.json())

    # 4. Indirect cycle: /page-b -> /page-c, then /page-c -> /page-a rejected
    r2 = client.post(
        list_url,
        {"source_path": "/page-b", "target_url": "/page-c"},
        format="json",
    )
    assert r2.status_code == status.HTTP_201_CREATED

    indirect_cycle = client.post(
        list_url,
        {"source_path": "/page-c", "target_url": "/page-a"},
        format="json",
    )
    assert indirect_cycle.status_code == status.HTTP_400_BAD_REQUEST
    assert "Redirect loop detected" in str(indirect_cycle.json())


@pytest.mark.django_db
def test_redirect_chain_depth_limit(redirect_setup: dict[str, object]) -> None:
    client = APIClient()
    admin = redirect_setup["admin"]
    workspace = redirect_setup["workspace"]
    site = redirect_setup["site"]
    assert isinstance(workspace, Workspace)
    assert isinstance(site, Site)

    client.force_authenticate(user=admin)
    list_url = reverse(
        "seo:redirect_rule_list_create", kwargs={"workspace_id": workspace.id, "site_id": site.id}
    )

    # Create 5 hops: /h1 -> /h2 -> /h3 -> /h4 -> /h5 -> /h6
    for i in range(1, 5):
        resp = client.post(
            list_url,
            {"source_path": f"/h{i}", "target_url": f"/h{i + 1}"},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED

    # Attempting to add 6th hop exceeds 5 hops limit
    resp_too_long = client.post(
        list_url,
        {"source_path": "/h5", "target_url": "/h6"},
        format="json",
    )
    assert resp_too_long.status_code == status.HTTP_400_BAD_REQUEST
    assert "chain too long" in str(resp_too_long.json())


@pytest.mark.django_db
def test_open_redirect_prevention(redirect_setup: dict[str, object]) -> None:
    client = APIClient()
    admin = redirect_setup["admin"]
    workspace = redirect_setup["workspace"]
    site = redirect_setup["site"]
    assert isinstance(workspace, Workspace)
    assert isinstance(site, Site)

    client.force_authenticate(user=admin)
    list_url = reverse(
        "seo:redirect_rule_list_create", kwargs={"workspace_id": workspace.id, "site_id": site.id}
    )

    # 1. External phishing destination rejected
    phish_resp = client.post(
        list_url,
        {"source_path": "/promo", "target_url": "https://malicious-phishing.org/login"},
        format="json",
    )
    assert phish_resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "Open redirect prohibited" in str(phish_resp.json())

    # 2. Redirect to registered domain on site accepted
    ok_domain = client.post(
        list_url,
        {"source_path": "/promo", "target_url": "https://redirect.portal.org/new-promo"},
        format="json",
    )
    assert ok_domain.status_code == status.HTTP_201_CREATED

    # 3. Redirect to allowed origin accepted
    ok_origin = client.post(
        list_url,
        {"source_path": "/assets-link", "target_url": "https://cdn.partner.com/images"},
        format="json",
    )
    assert ok_origin.status_code == status.HTTP_201_CREATED
