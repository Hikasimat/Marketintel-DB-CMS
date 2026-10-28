"""Sensitive logging redaction tests (FND-5, SEC-4)."""

from __future__ import annotations

import json
import logging

import pytest

from apps.common.logging import JSONFormatter, redact_sensitive


@pytest.mark.req("FND-5")
def test_redact_sensitive_cleans_passwords_and_tokens() -> None:
    payload = {
        "email": "user@example.com",
        "password": "supersecretpassword",
        "nested": {
            "api_key": "live_1234567890",
            "token": "tok_abcdef",
            "safe_field": "visible_value",
        },
        "items": [
            {"authorization": "Bearer eyJhbGciOi...", "amount": 100},
            {"other": "normal"},
        ],
    }
    cleaned = redact_sensitive(payload)

    assert cleaned["email"] == "user@example.com"
    assert cleaned["password"] == "[REDACTED]"
    assert cleaned["nested"]["api_key"] == "[REDACTED]"
    assert cleaned["nested"]["token"] == "[REDACTED]"
    assert cleaned["nested"]["safe_field"] == "visible_value"
    assert cleaned["items"][0]["authorization"] == "[REDACTED]"
    assert cleaned["items"][0]["amount"] == 100


@pytest.mark.req("FND-5")
def test_redact_sensitive_bearer_string() -> None:
    msg = "User logged in with header: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz"
    cleaned = redact_sensitive(msg)
    assert "eyJhbGci" not in cleaned
    assert "Bearer [REDACTED]" in cleaned


@pytest.mark.req("FND-5")
def test_json_formatter_produces_valid_json_with_correlation() -> None:
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="apps.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Test message with Bearer token12345",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-json-test"  # type: ignore[attr-defined]
    record.actor_id = "user-123"  # type: ignore[attr-defined]
    record.payload = {"secret": "secretval"}  # type: ignore[attr-defined]

    formatted = formatter.format(record)
    parsed = json.loads(formatted)

    assert parsed["level"] == "INFO"
    assert parsed["request_id"] == "req-json-test"
    assert parsed["actor_id"] == "user-123"
    assert "token12345" not in parsed["message"]
    assert parsed["payload"]["secret"] == "[REDACTED]"
