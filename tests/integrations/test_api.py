"""API integration and security tests for search integrations endpoints."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.integrations.models import (
    ConnectionStatus,
    IndexNowKey,
    SearchEngineConnection,
    SearchProvider,
)
from apps.sites.models import Domain, Site
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole


@pytest.fixture
def api_setup(db: None) -> dict[str, object]:
    admin = User.objects.create_user(email="admin@integrations.org", password="SecurePassword123!")
    viewer = User.objects.create_user(
        email="viewer@integrations.org", password="SecurePassword123!"
    )
    outside_user = User.objects.create_user(
        email="outsider@other.org", password="SecurePassword123!"
    )

    workspace = Workspace.objects.create(name="Integration Workspace", slug="integration-ws")
    WorkspaceMembership.objects.create(workspace=workspace, user=admin, role=WorkspaceRole.ADMIN)
    WorkspaceMembership.objects.create(workspace=workspace, user=viewer, role=WorkspaceRole.ANALYST)

    site = Site.objects.create(workspace=workspace, name="My Blog", slug="my-blog")
    domain = Domain.objects.create(
        site=site, hostname="blog.example.com", is_verified=True, is_primary=True
    )

    return {
        "admin": admin,
        "viewer": viewer,
        "outside_user": outside_user,
        "workspace": workspace,
        "site": site,
        "domain": domain,
    }


@pytest.mark.django_db
def test_connection_list_and_create(api_setup: dict[str, object]) -> None:
    client = APIClient()
    admin = api_setup["admin"]
    viewer = api_setup["viewer"]
    workspace = api_setup["workspace"]
    site = api_setup["site"]
    assert isinstance(workspace, Workspace)
    assert isinstance(site, Site)

    url = reverse(
        "integrations:connection_list_create",
        kwargs={"workspace_id": workspace.id, "site_id": site.id},
    )

    # 1. Viewer can list connections (initially empty)
    client.force_authenticate(user=viewer)
    resp = client.get(url)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json() == []

    # 2. Viewer cannot create connection (requires admin)
    resp = client.post(
        url,
        {
            "provider": SearchProvider.GOOGLE,
            "credentials": "secret-google-token",
        },
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    # 3. Admin can create connection
    client.force_authenticate(user=admin)
    resp = client.post(
        url,
        {
            "provider": SearchProvider.GOOGLE,
            "credentials": "secret-google-token",
            "settings": {"site_property": "sc-domain:example.com"},
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED
    data = resp.json()
    assert data["provider"] == SearchProvider.GOOGLE
    # Verify credential is not leaked in response
    assert "credentials" not in data or data.get("credentials") is None

    conn = SearchEngineConnection.objects.get(id=data["id"])
    assert conn.get_credentials() == "secret-google-token"


@pytest.mark.django_db
def test_connection_detail_and_update(api_setup: dict[str, object]) -> None:
    client = APIClient()
    admin = api_setup["admin"]
    workspace = api_setup["workspace"]
    site = api_setup["site"]
    assert isinstance(workspace, Workspace)
    assert isinstance(site, Site)

    conn = SearchEngineConnection.objects.create(
        site=site,
        provider=SearchProvider.BING,
        status=ConnectionStatus.CONNECTED,
    )
    conn.set_credentials("original-api-key")
    conn.save()

    url = reverse(
        "integrations:connection_detail",
        kwargs={"workspace_id": workspace.id, "site_id": site.id, "connection_id": conn.id},
    )

    client.force_authenticate(user=admin)
    resp = client.patch(url, {"credentials": "updated-api-key"})
    assert resp.status_code == status.HTTP_200_OK

    conn.refresh_from_db()
    assert conn.get_credentials() == "updated-api-key"

    # Delete connection
    del_resp = client.delete(url)
    assert del_resp.status_code == status.HTTP_204_NO_CONTENT
    assert not SearchEngineConnection.objects.filter(id=conn.id).exists()


@pytest.mark.django_db
def test_indexnow_key_api(api_setup: dict[str, object]) -> None:
    client = APIClient()
    admin = api_setup["admin"]
    workspace = api_setup["workspace"]
    site = api_setup["site"]
    assert isinstance(workspace, Workspace)
    assert isinstance(site, Site)

    url = reverse(
        "integrations:indexnow_key",
        kwargs={"workspace_id": workspace.id, "site_id": site.id},
    )

    client.force_authenticate(user=admin)
    # 1. GET creates key if none exists
    resp = client.get(url)
    assert resp.status_code == status.HTTP_200_OK
    original_key = resp.json()["key"]
    assert len(original_key) == 32

    # 2. POST rotates key
    rotate_url = reverse(
        "integrations:indexnow_rotate",
        kwargs={"workspace_id": workspace.id, "site_id": site.id},
    )
    rot_resp = client.post(rotate_url)
    assert rot_resp.status_code == status.HTTP_200_OK
    new_key = rot_resp.json()["key"]
    assert len(new_key) == 32
    assert new_key != original_key


@pytest.mark.django_db
def test_manual_submission_and_domain_validation(api_setup: dict[str, object]) -> None:
    client = APIClient()
    admin = api_setup["admin"]
    workspace = api_setup["workspace"]
    site = api_setup["site"]
    assert isinstance(workspace, Workspace)
    assert isinstance(site, Site)

    url = reverse(
        "integrations:manual_submission",
        kwargs={"workspace_id": workspace.id, "site_id": site.id},
    )
    client.force_authenticate(user=admin)

    # 1. Rejects URLs from foreign domain
    resp = client.post(
        url,
        {
            "provider": SearchProvider.INDEXNOW,
            "urls": ["https://evil-unregistered.com/phishing"],
        },
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST

    # 2. Accepts registered site domain
    with patch("apps.integrations.views.submit_indexing_job.delay") as mock_delay:
        resp = client.post(
            url,
            {
                "provider": SearchProvider.INDEXNOW,
                "urls": ["https://blog.example.com/hello-world"],
            },
        )
        assert resp.status_code == status.HTTP_202_ACCEPTED
        assert mock_delay.called


@pytest.mark.django_db
def test_public_indexnow_key_file_delivery(api_setup: dict[str, object]) -> None:
    client = APIClient()
    site = api_setup["site"]
    assert isinstance(site, Site)

    key_obj = IndexNowKey.generate_for_site(site)

    # 1. Correct key file returns plain text
    url = reverse(
        "integrations:public_indexnow_key",
        kwargs={"site_slug": site.slug, "key_file": f"{key_obj.key}.txt"},
    )
    resp = client.get(url)
    assert resp.status_code == status.HTTP_200_OK
    assert resp["Content-Type"].startswith("text/plain")
    assert resp.content.decode("utf-8") == key_obj.key

    # 2. Mismatched key file returns 404
    bad_url = reverse(
        "integrations:public_indexnow_key",
        kwargs={"site_slug": site.slug, "key_file": "wrongkey12345.txt"},
    )
    bad_resp = client.get(bad_url)
    assert bad_resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_inspect_url_endpoint(api_setup: dict[str, object]) -> None:
    client = APIClient()
    admin = api_setup["admin"]
    workspace = api_setup["workspace"]
    site = api_setup["site"]
    assert isinstance(workspace, Workspace)
    assert isinstance(site, Site)

    conn = SearchEngineConnection.objects.create(
        site=site,
        provider=SearchProvider.GOOGLE,
    )
    conn.set_credentials("fake-token")
    conn.save()

    url = reverse(
        "integrations:inspect_url",
        kwargs={"workspace_id": workspace.id, "site_id": site.id},
    )
    client.force_authenticate(user=admin)

    with patch("apps.integrations.views.GoogleSearchConsoleAdapter.inspect_url") as mock_inspect:
        mock_inspect.return_value = {
            "status": "SUCCESS",
            "verdict": "PASS",
            "coverage_state": "Indexed",
        }
        resp = client.post(url, {"url": "https://blog.example.com/page-1"})
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["verdict"] == "PASS"
