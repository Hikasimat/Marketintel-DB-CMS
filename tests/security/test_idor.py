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
