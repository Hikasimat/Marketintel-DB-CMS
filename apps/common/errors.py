"""Uniform error handling and envelope formatting (FND-4)."""

from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import set_rollback

from .logging import current_request_id

logger = logging.getLogger("apps.common.errors")


def format_error_payload(
    code: str,
    message: str,
    details: dict[str, Any] | list[Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Constructs the canonical error payload dictionary."""
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details if details is not None else {},
            "request_id": request_id or current_request_id.get() or "-",
        }
    }


error_envelope = format_error_payload


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """DRF custom exception handler returning the uniform error envelope."""
    request = context.get("request")
    req_id = getattr(request, "request_id", None) or current_request_id.get() or "-"

    # Translate Django core exceptions to DRF exceptions
    if isinstance(exc, Http404):
        exc = exceptions.NotFound(*(exc.args))
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied(*(exc.args))

    if isinstance(exc, exceptions.APIException):
        set_rollback()

        # Classify error code and status
        status_code = exc.status_code
        code = getattr(exc, "default_code", "api_error")
        message = str(exc.detail) if isinstance(exc.detail, (str, bytes)) else "An error occurred."
        details: Any = {}

        if isinstance(exc, exceptions.ValidationError):
            code = "validation_error"
            message = "Validation failed for one or more fields."
            details = exc.detail
        elif isinstance(exc, exceptions.AuthenticationFailed):
            code = "authentication_failed"
            if isinstance(exc.detail, dict):
                code = str(exc.detail.get("code", "authentication_failed"))
                message = str(exc.detail.get("message", message))
        elif isinstance(exc, exceptions.NotAuthenticated):
            code = "not_authenticated"
            message = "Authentication credentials were not provided."
        elif isinstance(exc, exceptions.PermissionDenied):
            code = "permission_denied"
        elif isinstance(exc, exceptions.NotFound):
            code = "not_found"
        elif isinstance(exc, exceptions.MethodNotAllowed):
            code = "method_not_allowed"
        elif isinstance(exc, exceptions.Throttled):
            code = "request_throttled"
            wait = getattr(exc, "wait", None)
            details = {"wait_seconds": wait} if wait is not None else {}
        elif status_code == 409:
            code = "conflict"

        payload = format_error_payload(
            code=code, message=message, details=details, request_id=req_id
        )
        return Response(payload, status=status_code, headers=getattr(exc, "headers", None))

    # Unhandled exceptions (500)
    logger.exception("Unhandled server exception: %s", exc, extra={"request_id": req_id})
    payload = format_error_payload(
        code="internal_server_error",
        message="An unexpected server error occurred.",
        details={},
        request_id=req_id,
    )
    return Response(payload, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
