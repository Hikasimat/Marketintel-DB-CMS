"""Immutable audit trail log model."""

from __future__ import annotations

import uuid
from typing import Any, ClassVar

from django.db import models


class AuditEvent(models.Model):
    """Immutable audit record tracking operational and security actions."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace_id = models.UUIDField(null=True, blank=True, db_index=True)
    actor_id = models.UUIDField(null=True, blank=True, db_index=True)
    actor_email = models.CharField(max_length=255, blank=True)
    action = models.CharField(max_length=100, db_index=True)
    resource_type = models.CharField(max_length=100, db_index=True)
    resource_id = models.CharField(max_length=255, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    payload = models.JSONField(default=dict)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "audit_event"
        ordering = ("-timestamp",)
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["workspace_id", "timestamp"]),
            models.Index(fields=["action", "timestamp"]),
        ]

    def __str__(self) -> str:
        actor = self.actor_email or str(self.actor_id)
        return f"AuditEvent({self.action}, actor={actor}, ts={self.timestamp})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk and AuditEvent.objects.filter(pk=self.pk).exists():
            raise RuntimeError("AuditEvent records are immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise RuntimeError("AuditEvent records are immutable and cannot be deleted.")
