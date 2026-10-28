"""Tests for multi-tenant workspace management and RBAC permissions."""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole

pytestmark = pytest.mark.django_db


def test_workspace_creation_assigns_owner_role():
    client = APIClient()
    user = User.objects.create_user(email="founder@example.com", password="SecurePassword123!")
    client.force_authenticate(user=user)

    url = reverse("tenancy:workspace_list_create")
    response = client.post(url, {"name": "Acme Corp", "slug": "acme-corp"}, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["name"] == "Acme Corp"
    assert data["slug"] == "acme-corp"
    assert data["current_user_role"] == "OWNER"

    # Verify membership in DB
    membership = WorkspaceMembership.objects.get(workspace_id=data["id"], user=user)
    assert membership.role == WorkspaceRole.OWNER


def test_workspace_rbac_role_hierarchy():
    owner = User.objects.create_user(email="owner@example.com", password="SecurePassword123!")
    admin = User.objects.create_user(email="admin@example.com", password="SecurePassword123!")
    editor = User.objects.create_user(email="editor@example.com", password="SecurePassword123!")
    analyst = User.objects.create_user(email="analyst@example.com", password="SecurePassword123!")

    workspace = Workspace.objects.create(name="Tenant One", slug="tenant-one")
    WorkspaceMembership.objects.create(workspace=workspace, user=owner, role=WorkspaceRole.OWNER)
    WorkspaceMembership.objects.create(workspace=workspace, user=admin, role=WorkspaceRole.ADMIN)
    WorkspaceMembership.objects.create(workspace=workspace, user=editor, role=WorkspaceRole.EDITOR)
    WorkspaceMembership.objects.create(
        workspace=workspace, user=analyst, role=WorkspaceRole.ANALYST
    )

    ws_url = reverse("tenancy:workspace_detail", kwargs={"workspace_id": workspace.id})
    members_url = reverse(
        "tenancy:workspace_member_list_create", kwargs={"workspace_id": workspace.id}
    )

    # 1. READ: All members can GET workspace details
    client = APIClient()
    for u in (owner, admin, editor, analyst):
        client.force_authenticate(user=u)
        assert client.get(ws_url).status_code == status.HTTP_200_OK

    # 2. UPDATE: Only OWNER and ADMIN can PATCH workspace; EDITOR and ANALYST get 403
    client.force_authenticate(user=editor)
    assert (
        client.patch(ws_url, {"name": "Editor Name"}, format="json").status_code
        == status.HTTP_403_FORBIDDEN
    )

    client.force_authenticate(user=analyst)
    assert (
        client.patch(ws_url, {"name": "Analyst Name"}, format="json").status_code
        == status.HTTP_403_FORBIDDEN
    )

    client.force_authenticate(user=admin)
    assert (
        client.patch(ws_url, {"name": "Admin Name"}, format="json").status_code
        == status.HTTP_200_OK
    )

    # 3. MEMBER MANAGEMENT: Only ADMIN/OWNER can invite members; EDITOR and ANALYST get 403
    client.force_authenticate(user=editor)
    assert (
        client.post(
            members_url, {"email": "new@example.com", "role": "EDITOR"}, format="json"
        ).status_code
        == status.HTTP_403_FORBIDDEN
    )

    client.force_authenticate(user=admin)
    invite_resp = client.post(
        members_url, {"email": "new@example.com", "role": "EDITOR"}, format="json"
    )
    assert invite_resp.status_code == status.HTTP_201_CREATED

    # 4. DELETE: Only OWNER can DELETE workspace; ADMIN gets 403
    client.force_authenticate(user=admin)
    assert client.delete(ws_url).status_code == status.HTTP_403_FORBIDDEN

    client.force_authenticate(user=owner)
    assert client.delete(ws_url).status_code == status.HTTP_204_NO_CONTENT


def test_cannot_remove_or_demote_last_owner():
    client = APIClient()
    owner = User.objects.create_user(email="soleowner@example.com", password="SecurePassword123!")
    workspace = Workspace.objects.create(name="Sole Owner WS", slug="sole-owner-ws")
    membership = WorkspaceMembership.objects.create(
        workspace=workspace, user=owner, role=WorkspaceRole.OWNER
    )

    client.force_authenticate(user=owner)
    member_detail_url = reverse(
        "tenancy:workspace_member_detail",
        kwargs={"workspace_id": workspace.id, "member_id": membership.id},
    )

    # Demoting last owner returns 400
    demote_resp = client.patch(member_detail_url, {"role": WorkspaceRole.ADMIN}, format="json")
    assert demote_resp.status_code == status.HTTP_400_BAD_REQUEST

    # Removing last owner returns 400
    remove_resp = client.delete(member_detail_url)
    assert remove_resp.status_code == status.HTTP_400_BAD_REQUEST
