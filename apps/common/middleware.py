"""Common middleware: request correlation and access logging."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from .logging import (
    current_actor_id,
    current_request_id,
)

logger = logging.getLogger("apps.common.access")


class RequestIDMiddleware:
    """Assigns or propagates X-Request-ID for distributed tracing and logging."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming_id = request.headers.get("X-Request-ID")
        if incoming_id and len(incoming_id) <= 64 and (incoming_id.isalnum() or "-" in incoming_id):
            request_id = incoming_id.strip()
        else:
            request_id = str(uuid.uuid4())

        request.request_id = request_id  # type: ignore[attr-defined]
        token = current_request_id.set(request_id)

        try:
            response = self.get_response(request)
        finally:
            current_request_id.reset(token)

        response.headers["X-Request-ID"] = request_id
        return response


class AccessLogMiddleware:
    """Logs incoming HTTP requests with latency, status, and redacted actor details."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        start_time = time.monotonic()

        # Set user context if already resolved or anonymous
        actor_token = None
        user = getattr(request, "user", None)
        if user and getattr(user, "is_authenticated", False):
            actor_token = current_actor_id.set(str(getattr(user, "id", "-")))

        try:
            response = self.get_response(request)
        finally:
            duration_ms = round((time.monotonic() - start_time) * 1000, 2)
            req_id = getattr(request, "request_id", "-")

            # Do not log health check probes unless they fail
            is_health = request.path.startswith("/health/")
            status_code = getattr(response, "status_code", 500)

            if not is_health or status_code >= 400:
                logger.info(
                    "%s %s %d (%.2f ms)",
                    request.method,
                    request.path,
                    status_code,
                    duration_ms,
                    extra={
                        "request_id": req_id,
                        "duration_ms": duration_ms,
                        "status_code": status_code,
                        "method": request.method,
                        "path": request.path,
                    },
                )

            if actor_token:
                current_actor_id.reset(actor_token)

        return response
