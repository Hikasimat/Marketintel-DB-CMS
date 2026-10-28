"""Views for Workspace lifecycle and membership management."""

from __future__ import annotations

import uuid
from typing import Any

from django.db import transaction
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.audit.services import record_audit_event
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole
from apps.tenancy.permissions import (
    IsWorkspaceAdmin,
    IsWorkspaceMember,
    IsWorkspaceOwner,
    resolve_workspace,
)
from apps.tenancy.serializers import (
    WorkspaceCreateSerializer,
    WorkspaceMemberAddSerializer,
    WorkspaceMembershipSerializer,
    WorkspaceMemberUpdateSerializer,
    WorkspaceSerializer,
)


class WorkspaceListCreateView(APIView):
    """List workspaces the user belongs to, or create a new workspace."""

    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(
        responses={200: WorkspaceSerializer(many=True)},
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        user = request.user
        if not isinstance(user, User):
            return Response([], status=status.HTTP_200_OK)
        memberships = (
            WorkspaceMembership.objects.filter(user=user)
            .select_related("workspace")
            .order_by("workspace__name")
        )
        workspaces = [m.workspace for m in memberships]
        serializer = WorkspaceSerializer(workspaces, many=True, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        request=WorkspaceCreateSerializer,
        responses={
            201: WorkspaceSerializer,
            400: OpenApiResponse(description="Validation error"),
        },
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        user = request.user
        if not isinstance(user, User):
            raise ValidationError("User not authenticated.")

        serializer = WorkspaceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            workspace = serializer.save()
            membership = WorkspaceMembership.objects.create(
                workspace=workspace,
                user=user,
                role=WorkspaceRole.OWNER,
            )
            setattr(request, "workspace", workspace)
            setattr(request, "workspace_membership", membership)

            record_audit_event(
                action="workspace.created",
                request=request,
                workspace_id=workspace.id,
                resource_type="workspace",
                resource_id=str(workspace.id),
                payload={"name": workspace.name, "slug": workspace.slug},
            )

        output_serializer = WorkspaceSerializer(workspace, context={"request": request})
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)


class WorkspaceDetailView(APIView):
    """Retrieve, update, or delete a specific workspace."""

    def get_permissions(self) -> list[permissions.BasePermission]:
        if self.request.method in ("PATCH", "PUT"):
            return [permissions.IsAuthenticated(), IsWorkspaceAdmin()]
        if self.request.method == "DELETE":
            return [permissions.IsAuthenticated(), IsWorkspaceOwner()]
        return [permissions.IsAuthenticated(), IsWorkspaceMember()]

    @extend_schema(
        responses={
            200: WorkspaceSerializer,
            404: OpenApiResponse(description="Workspace not found"),
        }
    )
    def get(self, request: Request, workspace_id: str, *args: Any, **kwargs: Any) -> Response:
        workspace = resolve_workspace(request, self)
        serializer = WorkspaceSerializer(workspace, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(request=WorkspaceCreateSerializer, responses={200: WorkspaceSerializer})
    def patch(self, request: Request, workspace_id: str, *args: Any, **kwargs: Any) -> Response:
        workspace = resolve_workspace(request, self)
        serializer = WorkspaceCreateSerializer(workspace, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_ws = serializer.save()

        record_audit_event(
            action="workspace.updated",
            request=request,
            workspace_id=workspace.id,
            resource_type="workspace",
            resource_id=str(workspace.id),
            payload={"changes": request.data},
        )
        return Response(WorkspaceSerializer(updated_ws, context={"request": request}).data)

    @extend_schema(responses={204: OpenApiResponse(description="Workspace deleted")})
    def delete(self, request: Request, workspace_id: str, *args: Any, **kwargs: Any) -> Response:
        workspace = resolve_workspace(request, self)
        ws_id = str(workspace.id)

        record_audit_event(
            action="workspace.deleted",
            request=request,
            workspace_id=workspace.id,
            resource_type="workspace",
            resource_id=ws_id,
            payload={"name": workspace.name},
        )
        workspace.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkspaceMemberListCreateView(APIView):
    """List or invite/add members in a workspace."""

    def get_permissions(self) -> list[permissions.BasePermission]:
        if self.request.method == "POST":
            return [permissions.IsAuthenticated(), IsWorkspaceAdmin()]
        return [permissions.IsAuthenticated(), IsWorkspaceMember()]

    @extend_schema(responses={200: WorkspaceMembershipSerializer(many=True)})
    def get(self, request: Request, workspace_id: str, *args: Any, **kwargs: Any) -> Response:
        workspace = resolve_workspace(request, self)
        memberships = (
            WorkspaceMembership.objects.filter(workspace=workspace)
            .select_related("user")
            .order_by("user__email")
        )
        serializer = WorkspaceMembershipSerializer(memberships, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        request=WorkspaceMemberAddSerializer,
        responses={201: WorkspaceMembershipSerializer},
    )
    def post(self, request: Request, workspace_id: str, *args: Any, **kwargs: Any) -> Response:
        workspace = resolve_workspace(request, self)
        serializer = WorkspaceMemberAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].lower().strip()
        role = serializer.validated_data["role"]

        user, _ = User.objects.get_or_create(email=email)

        if WorkspaceMembership.objects.filter(workspace=workspace, user=user).exists():
            raise ValidationError({"email": ["User is already a member of this workspace."]})

        membership = WorkspaceMembership.objects.create(
            workspace=workspace,
            user=user,
            role=role,
        )

        record_audit_event(
            action="workspace.member_added",
            request=request,
            workspace_id=workspace.id,
            resource_type="membership",
            resource_id=str(membership.id),
            payload={"user_email": email, "role": role},
        )

        return Response(
            WorkspaceMembershipSerializer(membership).data, status=status.HTTP_201_CREATED
        )


class WorkspaceMemberDetailView(APIView):
    """Change member role or remove member from workspace."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceAdmin)

    def _get_membership(self, workspace: Workspace, member_id: Any) -> WorkspaceMembership:
        if isinstance(member_id, uuid.UUID):
            m_id = member_id
        else:
            try:
                m_id = uuid.UUID(str(member_id))
            except ValueError as exc:
                raise NotFound("Member not found.") from exc

        membership = (
            WorkspaceMembership.objects.filter(workspace=workspace, id=m_id)
            .select_related("user")
            .first()
        )
        if membership is None:
            raise NotFound("Member not found in workspace.")
        return membership

    @extend_schema(
        request=WorkspaceMemberUpdateSerializer, responses={200: WorkspaceMembershipSerializer}
    )
    def patch(
        self, request: Request, workspace_id: str, member_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        workspace = resolve_workspace(request, self)
        membership = self._get_membership(workspace, member_id)

        serializer = WorkspaceMemberUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_role = serializer.validated_data["role"]

        # Prevent demoting the last owner
        if membership.role == WorkspaceRole.OWNER and new_role != WorkspaceRole.OWNER:
            owner_count = WorkspaceMembership.objects.filter(
                workspace=workspace, role=WorkspaceRole.OWNER
            ).count()
            if owner_count <= 1:
                raise ValidationError("Cannot demote the last owner of a workspace.")

        membership.role = new_role
        membership.save(update_fields=["role", "updated_at"])

        record_audit_event(
            action="workspace.member_updated",
            request=request,
            workspace_id=workspace.id,
            resource_type="membership",
            resource_id=str(membership.id),
            payload={"user_email": membership.user.email, "new_role": new_role},
        )

        return Response(WorkspaceMembershipSerializer(membership).data, status=status.HTTP_200_OK)

    @extend_schema(responses={204: OpenApiResponse(description="Member removed")})
    def delete(
        self, request: Request, workspace_id: str, member_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        workspace = resolve_workspace(request, self)
        membership = self._get_membership(workspace, member_id)

        # Prevent removing the last owner
        if membership.role == WorkspaceRole.OWNER:
            owner_count = WorkspaceMembership.objects.filter(
                workspace=workspace, role=WorkspaceRole.OWNER
            ).count()
            if owner_count <= 1:
                raise ValidationError("Cannot remove the last owner of a workspace.")

        user_email = membership.user.email
        membership_id = str(membership.id)
        membership.delete()

        record_audit_event(
            action="workspace.member_removed",
            request=request,
            workspace_id=workspace.id,
            resource_type="membership",
            resource_id=membership_id,
            payload={"user_email": user_email},
        )

        return Response(status=status.HTTP_204_NO_CONTENT)
