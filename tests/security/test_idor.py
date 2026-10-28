"""Security tests verifying cross-tenant isolation and anti-enumeration (IDOR).

Requirement TEN-3: Cross-tenant requests must return HTTP 404 Not Found rather
than HTTP 403 Forbidden to prevent tenant existence enumeration.
"""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole

pytestmark = pytest.mark.django_db


def test_cross_tenant_workspace_access_returns_404_not_403():
    client = APIClient()

    # Tenant A
    user_a = User.objects.create_user(email="user_a@tenant-a.com", password="SecurePassword123!")
    workspace_a = Workspace.objects.create(name="Tenant A", slug="tenant-a")
    WorkspaceMembership.objects.create(workspace=workspace_a, user=user_a, role=WorkspaceRole.OWNER)

    # Tenant B
    user_b = User.objects.create_user(email="user_b@tenant-b.com", password="SecurePassword123!")
    workspace_b = Workspace.objects.create(name="Tenant B", slug="tenant-b")
    WorkspaceMembership.objects.create(workspace=workspace_b, user=user_b, role=WorkspaceRole.OWNER)

    # User A tries to access Workspace B details
    client.force_authenticate(user=user_a)
    url_b = reverse("tenancy:workspace_detail", kwargs={"workspace_id": workspace_b.id})
    response = client.get(url_b)

    # Must be 404 Not Found to prevent enumeration
    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    assert data["error"]["code"] == "not_found"


def test_cross_tenant_member_listing_returns_404():
    client = APIClient()

    user_a = User.objects.create_user(email="user_a@tenant-a.com", password="SecurePassword123!")
    workspace_a = Workspace.objects.create(name="Tenant A", slug="tenant-a")
    WorkspaceMembership.objects.create(workspace=workspace_a, user=user_a, role=WorkspaceRole.OWNER)

    user_b = User.objects.create_user(email="user_b@tenant-b.com", password="SecurePassword123!")
    workspace_b = Workspace.objects.create(name="Tenant B", slug="tenant-b")
    WorkspaceMembership.objects.create(workspace=workspace_b, user=user_b, role=WorkspaceRole.OWNER)

    client.force_authenticate(user=user_a)
    members_b_url = reverse(
        "tenancy:workspace_member_list_create", kwargs={"workspace_id": workspace_b.id}
    )
    response = client.get(members_b_url)

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_cross_tenant_audit_log_access_returns_404():
    client = APIClient()

    user_a = User.objects.create_user(email="user_a@tenant-a.com", password="SecurePassword123!")
    workspace_a = Workspace.objects.create(name="Tenant A", slug="tenant-a")
    WorkspaceMembership.objects.create(workspace=workspace_a, user=user_a, role=WorkspaceRole.OWNER)

    user_b = User.objects.create_user(email="user_b@tenant-b.com", password="SecurePassword123!")
    workspace_b = Workspace.objects.create(name="Tenant B", slug="tenant-b")
    WorkspaceMembership.objects.create(workspace=workspace_b, user=user_b, role=WorkspaceRole.OWNER)

    client.force_authenticate(user=user_a)
    audit_b_url = reverse("audit:workspace_audit_logs", kwargs={"workspace_id": workspace_b.id})
    response = client.get(audit_b_url)

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_tampered_x_workspace_id_header_returns_404():
    client = APIClient()

    user_a = User.objects.create_user(email="user_a@tenant-a.com", password="SecurePassword123!")
    workspace_a = Workspace.objects.create(name="Tenant A", slug="tenant-a")
    WorkspaceMembership.objects.create(workspace=workspace_a, user=user_a, role=WorkspaceRole.OWNER)

    workspace_b = Workspace.objects.create(name="Tenant B", slug="tenant-b")

    client.force_authenticate(user=user_a)
    # Even if User A tries to forge header X-Workspace-ID to Workspace B
    response = client.get(
        reverse("tenancy:workspace_detail", kwargs={"workspace_id": workspace_b.id}),
        HTTP_X_WORKSPACE_ID=str(workspace_b.id),
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_cross_tenant_site_and_domain_access_returns_404():
    client = APIClient()

    user_a = User.objects.create_user(email="user_a@tenant-a.com", password="SecurePassword123!")
    workspace_a = Workspace.objects.create(name="Tenant A", slug="tenant-a")
    WorkspaceMembership.objects.create(workspace=workspace_a, user=user_a, role=WorkspaceRole.OWNER)

    user_b = User.objects.create_user(email="user_b@tenant-b.com", password="SecurePassword123!")
    workspace_b = Workspace.objects.create(name="Tenant B", slug="tenant-b")
    WorkspaceMembership.objects.create(workspace=workspace_b, user=user_b, role=WorkspaceRole.OWNER)

    from apps.sites.models import Domain, Site

    site_b = Site.objects.create(workspace=workspace_b, name="Site B", slug="site-b")
    domain_b = Domain.objects.create(site=site_b, hostname="b.example.com")

    client.force_authenticate(user=user_a)

    # User A tries to access Workspace B's sites
    resp_sites = client.get(f"/api/v1/workspaces/{workspace_b.id}/sites/")
    assert resp_sites.status_code == status.HTTP_404_NOT_FOUND

    # User A tries to access Site B detail
    resp_site_detail = client.get(f"/api/v1/workspaces/{workspace_b.id}/sites/{site_b.id}/")
    assert resp_site_detail.status_code == status.HTTP_404_NOT_FOUND

    # User A tries to access Site B domains
    resp_domains = client.get(f"/api/v1/workspaces/{workspace_b.id}/sites/{site_b.id}/domains/")
    assert resp_domains.status_code == status.HTTP_404_NOT_FOUND

    # User A tries to verify Site B domain
    resp_verify = client.post(
        f"/api/v1/workspaces/{workspace_b.id}/sites/{site_b.id}/domains/{domain_b.id}/verify/"
    )
    assert resp_verify.status_code == status.HTTP_404_NOT_FOUND


def test_cross_tenant_article_and_media_access_returns_404():
    client = APIClient()

    user_a = User.objects.create_user(email="user_a@tenant-a.com", password="SecurePassword123!")
    workspace_a = Workspace.objects.create(name="Tenant A", slug="tenant-a")
    WorkspaceMembership.objects.create(workspace=workspace_a, user=user_a, role=WorkspaceRole.OWNER)

    user_b = User.objects.create_user(email="user_b@tenant-b.com", password="SecurePassword123!")
    workspace_b = Workspace.objects.create(name="Tenant B", slug="tenant-b")
    WorkspaceMembership.objects.create(workspace=workspace_b, user=user_b, role=WorkspaceRole.OWNER)

    from apps.content.models import Article, MediaAsset
    from apps.sites.models import Site

    site_b = Site.objects.create(workspace=workspace_b, name="Site B", slug="site-b")
    article_b = Article.objects.create(
        site=site_b, author=user_b, title="Article B", slug="article-b"
    )
    MediaAsset.objects.create(
        workspace=workspace_b,
        filename="b.png",
        content_type="image/png",
        file_size=1024,
        storage_path="uploads/b.png",
    )

    client.force_authenticate(user=user_a)

    # User A tries to access articles in Site B
    resp_articles = client.get(f"/api/v1/workspaces/{workspace_b.id}/sites/{site_b.id}/articles/")
    assert resp_articles.status_code == status.HTTP_404_NOT_FOUND

    # User A tries to access article detail
    resp_art_detail = client.get(
        f"/api/v1/workspaces/{workspace_b.id}/sites/{site_b.id}/articles/{article_b.id}/"
    )
    assert resp_art_detail.status_code == status.HTTP_404_NOT_FOUND

    # User A tries to access media assets in Workspace B
    resp_media = client.get(f"/api/v1/workspaces/{workspace_b.id}/media/")
    assert resp_media.status_code == status.HTTP_404_NOT_FOUND


def test_cross_site_article_isolation_within_workspace_returns_404():
    client = APIClient()

    user = User.objects.create_user(email="user@ws.com", password="SecurePassword123!")
    workspace = Workspace.objects.create(name="Tenant Multi", slug="tenant-multi")
    WorkspaceMembership.objects.create(workspace=workspace, user=user, role=WorkspaceRole.OWNER)

    from apps.content.models import Article
    from apps.sites.models import Site

    site1 = Site.objects.create(workspace=workspace, name="Site 1", slug="site-1")
    site2 = Site.objects.create(workspace=workspace, name="Site 2", slug="site-2")
    art_site1 = Article.objects.create(site=site1, author=user, title="Art 1", slug="art-1")

    client.force_authenticate(user=user)

    # Attempting to fetch Site 1's article through Site 2 URL
    resp = client.get(
        f"/api/v1/workspaces/{workspace.id}/sites/{site2.id}/articles/{art_site1.id}/"
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND
