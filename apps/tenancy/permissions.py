"""RBAC permissions enforcing multi-tenant isolation and role hierarchy."""

from __future__ import annotations

import uuid

from rest_framework import permissions
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole


def resolve_workspace(request: Request, view: APIView) -> Workspace:
    """Resolve target workspace from URL or request header.

    Raises NotFound (HTTP 404) if workspace does not exist or user is not a member,
    preventing tenant enumeration.
    """
    if hasattr(request, "workspace") and request.workspace is not None:
        return request.workspace

    workspace_id = view.kwargs.get("workspace_id") or request.headers.get("X-Workspace-ID")
    if not workspace_id:
        raise NotFound("Workspace not specified.")

    if isinstance(workspace_id, uuid.UUID):
        ws_uuid = workspace_id
    else:
        try:
            ws_uuid = uuid.UUID(str(workspace_id))
        except ValueError as exc:
            raise NotFound("Workspace not found.") from exc

    try:
        workspace = Workspace.objects.get(id=ws_uuid)
    except Workspace.DoesNotExist as exc:
        raise NotFound("Workspace not found.") from exc

    # Validate that requesting user is a member of this workspace
    user = request.user
    if not user or not user.is_authenticated:
        raise NotFound("Workspace not found.")

    membership = (
        WorkspaceMembership.objects.filter(workspace=workspace, user=user)
        .select_related("workspace", "user")
        .first()
    )

    if membership is None:
        # Non-members receive 404 (anti-enumeration, TEN-3)
        raise NotFound("Workspace not found.")

    setattr(request, "workspace", workspace)
    setattr(request, "workspace_membership", membership)
    return workspace


class IsWorkspaceMember(permissions.BasePermission):
    """Enforce that the authenticated user belongs to the target workspace."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        # Resolving workspace raises NotFound if non-member
        resolve_workspace(request, view)
        return True


class RequireWorkspaceRole(permissions.BasePermission):
    """Enforce minimum role rank within the resolved workspace."""

    min_role: WorkspaceRole = WorkspaceRole.EDITOR

    def __init__(self, min_role: WorkspaceRole | None = None) -> None:
        if min_role is not None:
            self.min_role = min_role

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False

        # Non-members get 404 here
        resolve_workspace(request, view)
        membership: WorkspaceMembership = getattr(request, "workspace_membership")

        if not membership.has_role(self.min_role):
            raise PermissionDenied(
                f"Action requires minimum role '{self.min_role.value}'."
                f" Current role: '{membership.role}'."
            )
        return True


class IsWorkspaceOwner(RequireWorkspaceRole):
    min_role = WorkspaceRole.OWNER


class IsWorkspaceAdmin(RequireWorkspaceRole):
    min_role = WorkspaceRole.ADMIN


class IsWorkspaceEditor(RequireWorkspaceRole):
    min_role = WorkspaceRole.EDITOR


class IsWorkspaceAnalyst(RequireWorkspaceRole):
    min_role = WorkspaceRole.ANALYST
