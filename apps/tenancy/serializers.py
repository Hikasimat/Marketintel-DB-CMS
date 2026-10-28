"""Serializers for workspaces and memberships."""

from __future__ import annotations

from typing import Any, ClassVar

from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole


class WorkspaceSerializer(serializers.ModelSerializer[Workspace]):
    current_user_role = serializers.SerializerMethodField()

    class Meta:
        model = Workspace
        fields = ("id", "name", "slug", "created_at", "updated_at", "current_user_role")
        read_only_fields = ("id", "created_at", "updated_at", "current_user_role")

    def get_current_user_role(self, obj: Workspace) -> str | None:
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            return None
        membership = getattr(request, "workspace_membership", None)
        if membership and membership.workspace_id == obj.id:
            return str(membership.role)
        m = WorkspaceMembership.objects.filter(workspace=obj, user=request.user).first()
        return str(m.role) if m else None


class WorkspaceCreateSerializer(serializers.ModelSerializer[Workspace]):
    class Meta:
        model = Workspace
        fields = ("name", "slug")
        extra_kwargs: ClassVar[dict[str, Any]] = {"slug": {"required": False}}


class WorkspaceMembershipSerializer(serializers.ModelSerializer[WorkspaceMembership]):
    user = UserSerializer(read_only=True)

    class Meta:
        model = WorkspaceMembership
        fields = ("id", "user", "role", "created_at", "updated_at")
        read_only_fields = ("id", "user", "created_at", "updated_at")


class WorkspaceMemberAddSerializer(serializers.Serializer[Any]):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=WorkspaceRole.choices, default=WorkspaceRole.EDITOR)


class WorkspaceMemberUpdateSerializer(serializers.Serializer[Any]):
    role = serializers.ChoiceField(choices=WorkspaceRole.choices)
