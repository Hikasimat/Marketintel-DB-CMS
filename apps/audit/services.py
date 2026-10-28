"""Service functions for logging immutable audit events."""

from __future__ import annotations

import uuid
from typing import Any

from django.http import HttpRequest

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.common.logging import redact_sensitive


def record_audit_event(
    action: str,
    *,
    request: HttpRequest | None = None,
    workspace_id: uuid.UUID | str | None = None,
    actor: User | None = None,
    resource_type: str = "",
    resource_id: str = "",
    payload: dict[str, Any] | None = None,
) -> AuditEvent:
    """Record an immutable audit event with automatic PII/secret scrubbing."""
    actor_id: uuid.UUID | None = None
    actor_email: str = ""

    if actor is not None and getattr(actor, "is_authenticated", False):
        actor_id = getattr(actor, "id", None)
        actor_email = getattr(actor, "email", "")
    elif request is not None and getattr(request, "user", None) and request.user.is_authenticated:
        actor_id = getattr(request.user, "id", None)
        actor_email = getattr(request.user, "email", "")

    ip_address: str | None = None
    user_agent: str = ""

    if request is not None:
        # Check HTTP_X_FORWARDED_FOR first
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            ip_address = forwarded.split(",")[0].strip()
        else:
            ip_address = request.META.get("REMOTE_ADDR")
        user_agent = request.META.get("HTTP_USER_AGENT", "")

    ws_uuid: uuid.UUID | None = None
    if workspace_id is not None:
        ws_uuid = uuid.UUID(str(workspace_id))

    cleaned_payload: dict[str, Any] = {}
    if payload:
        # Scrub passwords, tokens, and secrets from audit payloads
        cleaned_payload = redact_sensitive(payload)

    return AuditEvent.objects.create(
        workspace_id=ws_uuid,
        actor_id=actor_id,
        actor_email=actor_email,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id),
        ip_address=ip_address,
        user_agent=user_agent,
        payload=cleaned_payload,
    )
