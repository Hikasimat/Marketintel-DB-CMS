"""Workspace and membership models for multi-tenant isolation."""

from __future__ import annotations

import uuid
from typing import Any, ClassVar

from django.db import models
from django.utils.text import slugify

from apps.accounts.models import User


class WorkspaceRole(models.TextChoices):
    OWNER = "OWNER", "Owner"
    ADMIN = "ADMIN", "Admin"
    EDITOR = "EDITOR", "Editor"
    ANALYST = "ANALYST", "Analyst"

    @classmethod
    def get_rank(cls, role: str) -> int:
        ranks: dict[str, int] = {
            cls.OWNER.value: 40,
            cls.ADMIN.value: 30,
            cls.EDITOR.value: 20,
            cls.ANALYST.value: 10,
        }
        return ranks.get(str(role), 0)


class Workspace(models.Model):
    """Isolated tenant workspace representing a customer organization or team."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenancy_workspace"
        ordering = ("name",)

    def __str__(self) -> str:
        return f"{self.name} ({self.slug})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class WorkspaceMembership(models.Model):
    """Associates a User with a Workspace and assigns their RBAC role."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="workspace_memberships")
    role = models.CharField(
        max_length=20,
        choices=WorkspaceRole.choices,
        default=WorkspaceRole.EDITOR,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenancy_workspace_membership"
        unique_together = ("workspace", "user")
        ordering = ("-created_at",)
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["workspace", "role"]),
        ]

    def __str__(self) -> str:
        return f"Membership({self.user.email} in {self.workspace.name} as {self.role})"

    @property
    def rank(self) -> int:
        return WorkspaceRole.get_rank(self.role)

    def has_role(self, min_role: WorkspaceRole | str) -> bool:
        min_rank = WorkspaceRole.get_rank(str(min_role))
        return self.rank >= min_rank
