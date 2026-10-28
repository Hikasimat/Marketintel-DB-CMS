"""Structured logging, context management, and sensitive data redaction (FND-5)."""

from __future__ import annotations

import contextvars
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

# Context variables for request correlation
current_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_request_id", default=None
)
current_actor_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_actor_id", default=None
)
current_site_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_site_id", default=None
)
current_workspace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_workspace_id", default=None
)

REDACTED_STR = "[REDACTED]"

# Patterns and keys requiring redaction
SENSITIVE_KEY_PATTERN = re.compile(
    r"^(password|secret|token|api_key|authorization|cookie|sessionid|refresh|access_token|key|consent_payload|categories_payload|.*private_key.*|github_private_key|webhook_secret)$",
    re.IGNORECASE,
)
SENSITIVE_HEADER_PATTERN = re.compile(
    r"^(authorization|cookie|set-cookie|x-api-key|proxy-authorization)$",
    re.IGNORECASE,
)
BEARER_PATTERN = re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE)


def redact_sensitive(obj: Any) -> Any:
    """Recursively redacts sensitive fields from dicts, lists, and strings."""
    if isinstance(obj, dict):
        cleaned: dict[str, Any] = {}
        for k, v in obj.items():
            if isinstance(k, str) and SENSITIVE_KEY_PATTERN.search(k):
                cleaned[k] = REDACTED_STR
            else:
                cleaned[k] = redact_sensitive(v)
        return cleaned
    if isinstance(obj, list):
        return [redact_sensitive(item) for item in obj]
    if isinstance(obj, str):
        return BEARER_PATTERN.sub("Bearer [REDACTED]", obj)
    return obj


class RequestContextFilter(logging.Filter):
    """Injects contextual attributes into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = current_request_id.get() or getattr(record, "request_id", "-")
        record.actor_id = current_actor_id.get() or getattr(record, "actor_id", "-")
        record.site_id = current_site_id.get() or getattr(record, "site_id", "-")
        record.workspace_id = current_workspace_id.get() or getattr(record, "workspace_id", "-")
        return True


class JSONFormatter(logging.Formatter):
    """Produces structured JSON output with redaction and standard fields."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=UTC).isoformat()
        message = record.getMessage()
        if isinstance(message, str):
            message = BEARER_PATTERN.sub("Bearer [REDACTED]", message)

        data: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": message,
            "request_id": getattr(record, "request_id", "-"),
            "actor_id": getattr(record, "actor_id", "-"),
            "site_id": getattr(record, "site_id", "-"),
            "workspace_id": getattr(record, "workspace_id", "-"),
        }

        # Include extra payload if present
        if hasattr(record, "payload") and record.payload is not None:
            data["payload"] = redact_sensitive(record.payload)

        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)

        return json.dumps(data)


class RedactingConsoleFormatter(logging.Formatter):
    """Console formatter for development with sensitive data redaction."""

    def format(self, record: logging.LogRecord) -> str:
        orig_msg = record.msg
        if isinstance(record.msg, str):
            record.msg = BEARER_PATTERN.sub("Bearer [REDACTED]", record.msg)
        req_id = getattr(record, "request_id", "-")
        formatted = super().format(record)
        record.msg = orig_msg
        return f"[{record.levelname}] [req={req_id}] {formatted}"
