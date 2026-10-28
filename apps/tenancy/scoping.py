"""Tenant scoping managers, models, and view mixins."""

from __future__ import annotations

import uuid
from typing import Any, ClassVar, TypeVar

from django.db import models
from rest_framework.request import Request

from apps.tenancy.models import Workspace
from apps.tenancy.permissions import resolve_workspace

_M = TypeVar("_M", bound=models.Model)


class TenantScopedQuerySet(models.QuerySet[_M]):
    """QuerySet enforcing workspace-scoped filtering to prevent cross-tenant leakage."""

    def for_workspace(self, workspace: Workspace | uuid.UUID | str) -> TenantScopedQuerySet[_M]:
        ws_id = workspace.id if isinstance(workspace, Workspace) else uuid.UUID(str(workspace))
        return self.filter(workspace_id=ws_id)


class TenantScopedModel(models.Model):
    """Abstract base model for all resources owned by a tenant workspace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="%(class)ss")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantScopedQuerySet.as_manager()

    class Meta:
        abstract = True
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["workspace", "created_at"]),
        ]


class WorkspaceResolutionMixin:
    """DRF View mixin that resolves target workspace and caches it on the request."""

    request: Request
    kwargs: dict[str, Any]

    def get_workspace(self) -> Workspace:
        return resolve_workspace(self.request, self)  # type: ignore[arg-type]
