"""Tests for Site management, custom domains, and RFC 1123 hostname validation."""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.sites.models import Domain, Site
from apps.sites.validators import validate_hostname
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole

pytestmark = pytest.mark.django_db


def test_hostname_validator():
    # Valid hostnames
    assert validate_hostname("blog.example.org.uk") == "blog.example.org.uk"
    assert validate_hostname("my-subdomain.company.com") == "my-subdomain.company.com"
    assert validate_hostname("site123.tech") == "site123.tech"

    # Invalid: protocols or paths
    with pytest.raises(ValidationError, match="cannot include protocols"):
        validate_hostname("https://blog.example.com")

    with pytest.raises(ValidationError, match="cannot include protocols"):
        validate_hostname("blog.example.com/path")

    with pytest.raises(ValidationError, match="cannot include protocols"):
        validate_hostname("blog.example.com:8080")

    # Invalid: reserved hostnames
    with pytest.raises(ValidationError, match="reserved"):
        validate_hostname("localhost")

    with pytest.raises(ValidationError, match="reserved"):
        validate_hostname("127.0.0.1")

    with pytest.raises(ValidationError, match="reserved"):
        validate_hostname("example.com")


def test_site_lifecycle_and_rbac():
    client = APIClient()
    owner = User.objects.create_user(email="owner@tenant.com", password="SecurePassword123!")
    editor = User.objects.create_user(email="editor@tenant.com", password="SecurePassword123!")
    analyst = User.objects.create_user(email="analyst@tenant.com", password="SecurePassword123!")

    workspace = Workspace.objects.create(name="Web Org", slug="web-org")
    WorkspaceMembership.objects.create(workspace=workspace, user=owner, role=WorkspaceRole.OWNER)
    WorkspaceMembership.objects.create(workspace=workspace, user=editor, role=WorkspaceRole.EDITOR)
    WorkspaceMembership.objects.create(
        workspace=workspace, user=analyst, role=WorkspaceRole.ANALYST
    )

    sites_url = reverse("sites:site_list_create", kwargs={"workspace_id": workspace.id})

    # 1. Analyst cannot create site (403)
    client.force_authenticate(user=analyst)
    resp_analyst = client.post(
        sites_url, {"name": "Analyst Blog", "slug": "analyst-blog"}, format="json"
    )
    assert resp_analyst.status_code == status.HTTP_403_FORBIDDEN

    # 2. Editor can create site (201)
    client.force_authenticate(user=editor)
    create_resp = client.post(
        sites_url,
        {
            "name": "Tech Blog",
            "slug": "tech-blog",
            "default_locale": "en-US",
            "allowed_origins": ["https://techblog.com"],
        },
        format="json",
    )
    assert create_resp.status_code == status.HTTP_201_CREATED
    site_id = create_resp.json()["id"]

    site_url = reverse(
        "sites:site_detail", kwargs={"workspace_id": workspace.id, "site_id": site_id}
    )

    # 3. All members can retrieve site details
    client.force_authenticate(user=analyst)
    get_resp = client.get(site_url)
    assert get_resp.status_code == status.HTTP_200_OK
    assert get_resp.json()["name"] == "Tech Blog"

    # 4. Editor can update site
    client.force_authenticate(user=editor)
    patch_resp = client.patch(site_url, {"name": "Tech Insights"}, format="json")
    assert patch_resp.status_code == status.HTTP_200_OK
    assert patch_resp.json()["name"] == "Tech Insights"

    # 5. Editor cannot delete site (requires Admin/Owner)
    assert client.delete(site_url).status_code == status.HTTP_403_FORBIDDEN

    # 6. Owner can delete site
    client.force_authenticate(user=owner)
    assert client.delete(site_url).status_code == status.HTTP_204_NO_CONTENT


def test_domain_registration_and_verification():
    client = APIClient()
    admin = User.objects.create_user(email="admin@tenant.com", password="SecurePassword123!")
    workspace = Workspace.objects.create(name="Domain Org", slug="domain-org")
    WorkspaceMembership.objects.create(workspace=workspace, user=admin, role=WorkspaceRole.ADMIN)

    site = Site.objects.create(workspace=workspace, name="Main Site", slug="main-site")

    client.force_authenticate(user=admin)
    domains_url = reverse(
        "sites:domain_list_create",
        kwargs={"workspace_id": workspace.id, "site_id": site.id},
    )

    # Register custom domain
    reg_resp = client.post(
        domains_url,
        {"hostname": "news.portal.org", "is_primary": True},
        format="json",
    )
    assert reg_resp.status_code == status.HTTP_201_CREATED
    domain_data = reg_resp.json()
    domain_id = domain_data["id"]
    assert domain_data["hostname"] == "news.portal.org"
    assert domain_data["is_verified"] is False
    assert domain_data["is_primary"] is True
    assert "dns_verification_record" in domain_data
    assert domain_data["dns_verification_record"]["name"] == "_cms-verify.news.portal.org"

    verify_url = reverse(
        "sites:domain_verify",
        kwargs={"workspace_id": workspace.id, "site_id": site.id, "domain_id": domain_id},
    )

    # Verification failure simulation
    fail_verify_resp = client.post(verify_url, {"simulate_success": False}, format="json")
    assert fail_verify_resp.status_code == status.HTTP_400_BAD_REQUEST

    # Successful verification
    verify_resp = client.post(verify_url, {"simulate_success": True}, format="json")
    assert verify_resp.status_code == status.HTTP_200_OK
    verified_data = verify_resp.json()
    assert verified_data["is_verified"] is True
    assert verified_data["ssl_status"] == "ACTIVE"
    assert verified_data["verified_at"] is not None

    # Verify site primary domain is reflected
    site_url = reverse(
        "sites:site_detail", kwargs={"workspace_id": workspace.id, "site_id": site.id}
    )
    site_resp = client.get(site_url)
    assert site_resp.json()["primary_domain"] == "news.portal.org"

    # Verify model string representation and clean
    site.refresh_from_db()
    assert str(site) == "Main Site (main-site)"
    site.clean()

    domain = Domain.objects.get(id=domain_id)
    assert "verified" in str(domain)
    domain.clean()

    unverified_domain = Domain(site=site, hostname="unverified.example.org")
    assert "unverified" in str(unverified_domain)
