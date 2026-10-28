"""Uniform error formatting tests (FND-4)."""

from __future__ import annotations

import pytest
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.test import APIRequestFactory

from apps.common.errors import exception_handler, format_error_payload


@pytest.mark.req("FND-4")
def test_format_error_payload_envelope() -> None:
    payload = format_error_payload(
        code="test_code",
        message="A test message",
        details={"field": "invalid"},
        request_id="req-1234",
    )
    assert payload == {
        "error": {
            "code": "test_code",
            "message": "A test message",
            "details": {"field": "invalid"},
            "request_id": "req-1234",
        }
    }


@pytest.mark.req("FND-4")
def test_exception_handler_handles_validation_error() -> None:
    exc = exceptions.ValidationError({"title": ["This field is required."]})
    factory = APIRequestFactory()
    request = factory.get("/")
    request.request_id = "req-test-val"  # type: ignore[attr-defined]

    response = exception_handler(exc, {"request": request})
    assert response is not None
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    data = response.data
    assert data["error"]["code"] == "validation_error"
    assert data["error"]["request_id"] == "req-test-val"
    assert "title" in data["error"]["details"]


@pytest.mark.req("FND-4")
def test_exception_handler_handles_404_not_found() -> None:
    exc = Http404("Item does not exist.")
    factory = APIRequestFactory()
    request = factory.get("/")
    request.request_id = "req-404"  # type: ignore[attr-defined]

    response = exception_handler(exc, {"request": request})
    assert response is not None
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.data["error"]["code"] == "not_found"
    assert response.data["error"]["request_id"] == "req-404"


@pytest.mark.req("FND-4")
def test_exception_handler_handles_unhandled_500() -> None:
    exc = RuntimeError("Secret database crash details")
    factory = APIRequestFactory()
    request = factory.get("/")
    request.request_id = "req-500"  # type: ignore[attr-defined]

    response = exception_handler(exc, {"request": request})
    assert response is not None
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    data = response.data
    assert data["error"]["code"] == "internal_server_error"
    # Ensure sensitive runtime exception details are suppressed
    assert "Secret database crash details" not in str(data)
    assert data["error"]["request_id"] == "req-500"
