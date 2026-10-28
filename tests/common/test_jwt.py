"""Tests for pure-python RFC 7519 JWT implementation."""

import time

import pytest

from apps.common.jwt import (
    TokenExpiredError,
    TokenInvalidError,
    decode_jwt,
    encode_jwt,
)

SECRET = "super-secure-test-secret-at-least-256-bits-long-12345"
OTHER_SECRET = "different-secret-key-for-tamper-testing-abcdef"


def test_encode_and_decode_roundtrip():
    now = int(time.time())
    payload = {
        "sub": "user-uuid-123",
        "email": "test@example.com",
        "exp": now + 3600,
        "role": "admin",
    }
    token = encode_jwt(payload, secret=SECRET)
    assert isinstance(token, str)
    assert len(token.split(".")) == 3

    decoded = decode_jwt(token, secret=SECRET)
    assert decoded["sub"] == "user-uuid-123"
    assert decoded["email"] == "test@example.com"
    assert decoded["role"] == "admin"


def test_decode_with_wrong_secret_fails():
    now = int(time.time())
    token = encode_jwt({"sub": "user-123", "exp": now + 60}, secret=SECRET)

    with pytest.raises(TokenInvalidError, match="Invalid token signature"):
        decode_jwt(token, secret=OTHER_SECRET)


def test_decode_expired_token():
    past = int(time.time()) - 10
    token = encode_jwt({"sub": "user-123", "exp": past}, secret=SECRET)

    with pytest.raises(TokenExpiredError, match="Token has expired"):
        decode_jwt(token, secret=SECRET)


def test_decode_expired_token_with_leeway():
    past = int(time.time()) - 5
    token = encode_jwt({"sub": "user-123", "exp": past}, secret=SECRET)

    # With leeway=10, 5 seconds past is accepted
    decoded = decode_jwt(token, secret=SECRET, leeway=10)
    assert decoded["sub"] == "user-123"


def test_decode_tampered_payload():
    now = int(time.time())
    token = encode_jwt({"sub": "user-123", "role": "editor", "exp": now + 60}, secret=SECRET)
    parts = token.split(".")
    # Tamper with payload segment
    import base64
    import json

    tampered_bytes = json.dumps({"sub": "user-123", "role": "admin", "exp": now + 60}).encode(
        "utf-8"
    )
    tampered_b64 = base64.urlsafe_b64encode(tampered_bytes).rstrip(b"=").decode("ascii")
    tampered_token = f"{parts[0]}.{tampered_b64}.{parts[2]}"

    with pytest.raises(TokenInvalidError, match="Invalid token signature"):
        decode_jwt(tampered_token, secret=SECRET)


def test_decode_audience_and_issuer():
    now = int(time.time())
    token = encode_jwt(
        {"sub": "user-123", "iss": "cms-backend", "aud": "cms-client", "exp": now + 60},
        secret=SECRET,
    )

    # Valid aud & iss
    decoded = decode_jwt(token, secret=SECRET, audience="cms-client", issuer="cms-backend")
    assert decoded["sub"] == "user-123"

    # Invalid issuer
    with pytest.raises(TokenInvalidError, match="Token issuer"):
        decode_jwt(token, secret=SECRET, issuer="wrong-issuer")

    # Invalid audience
    with pytest.raises(TokenInvalidError, match="Audience"):
        decode_jwt(token, secret=SECRET, audience="wrong-aud")


def test_decode_malformed_token_segments():
    with pytest.raises(TokenInvalidError, match="Invalid JWT segment count"):
        decode_jwt("only.two", secret=SECRET)

    with pytest.raises(TokenInvalidError, match="Token must be a non-empty string"):
        decode_jwt("", secret=SECRET)
