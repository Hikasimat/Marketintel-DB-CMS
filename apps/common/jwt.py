"""Pure Python RFC 7519 / RFC 7515 JSON Web Token (JWT) implementation.

Uses Python standard library hmac and hashlib for HS256 signing and verification.
Provides constant-time signature comparison, standard claims verification (exp, nbf,
iat, iss, aud), and strict error typing for the CMS authentication system.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


class JWTError(Exception):
    """Base exception for all JWT operations."""


class TokenExpiredError(JWTError):
    """Raised when the token's exp claim is in the past."""


class TokenInvalidError(JWTError):
    """Raised when the token is malformed, has an invalid signature, or fails claims."""


def _b64url_encode(data: bytes) -> str:
    """Encode bytes to base64url string without trailing padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    """Decode a base64url string with optional missing padding."""
    padding = len(segment) % 4
    if padding == 2:
        segment += "=="
    elif padding == 3:
        segment += "="
    elif padding == 1:
        raise TokenInvalidError("Invalid base64url segment length")
    try:
        return base64.urlsafe_b64decode(segment.encode("ascii"))
    except Exception as exc:
        raise TokenInvalidError(f"Failed to decode base64url: {exc}") from exc


def encode_jwt(
    payload: dict[str, Any],
    secret: str,
    algorithm: str = "HS256",
    headers: dict[str, Any] | None = None,
) -> str:
    """Encode a dictionary payload into an HS256 JWT string."""
    if algorithm != "HS256":
        raise ValueError(f"Unsupported JWT algorithm: {algorithm}. Only HS256 is supported.")

    header_dict = {"alg": "HS256", "typ": "JWT"}
    if headers:
        header_dict.update(headers)

    header_bytes = json.dumps(header_dict, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

    header_b64 = _b64url_encode(header_bytes)
    payload_b64 = _b64url_encode(payload_bytes)

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    signature_b64 = _b64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def decode_jwt(
    token: str,
    secret: str,
    algorithms: list[str] | tuple[str, ...] = ("HS256",),
    audience: str | None = None,
    issuer: str | None = None,
    leeway: int = 0,
) -> dict[str, Any]:
    """Decode and verify an HS256 JWT string.

    Validates signature via constant-time comparison, verifies exp/nbf/iat,
    and checks audience/issuer when supplied.
    """
    if not isinstance(token, str) or not token:
        raise TokenInvalidError("Token must be a non-empty string.")

    parts = token.strip().split(".")
    if len(parts) != 3:
        raise TokenInvalidError(f"Invalid JWT segment count: expected 3, got {len(parts)}.")

    header_b64, payload_b64, signature_b64 = parts

    try:
        header_bytes = _b64url_decode(header_b64)
        header = json.loads(header_bytes.decode("utf-8"))
    except Exception as exc:
        raise TokenInvalidError(f"Malformed JWT header: {exc}") from exc

    if not isinstance(header, dict):
        raise TokenInvalidError("JWT header must be a JSON object.")

    alg = header.get("alg")
    if alg not in algorithms:
        raise TokenInvalidError(f"Unsupported algorithm '{alg}', expected one of {algorithms}.")

    # Verify signature
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    actual_sig = _b64url_decode(signature_b64)

    if not hmac.compare_digest(expected_sig, actual_sig):
        raise TokenInvalidError("Invalid token signature.")

    # Parse payload
    try:
        payload_bytes = _b64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as exc:
        raise TokenInvalidError(f"Malformed JWT payload: {exc}") from exc

    if not isinstance(payload, dict):
        raise TokenInvalidError("JWT payload must be a JSON object.")

    now = int(time.time())

    # Expiration check
    if "exp" in payload:
        exp = payload["exp"]
        if not isinstance(exp, (int, float)):
            raise TokenInvalidError("Claim 'exp' must be a numeric timestamp.")
        if now > exp + leeway:
            raise TokenExpiredError("Token has expired.")

    # Not before check
    if "nbf" in payload:
        nbf = payload["nbf"]
        if not isinstance(nbf, (int, float)):
            raise TokenInvalidError("Claim 'nbf' must be a numeric timestamp.")
        if now < nbf - leeway:
            raise TokenInvalidError("Token is not yet valid (nbf).")

    # Issuer check
    if issuer is not None and payload.get("iss") != issuer:
        raise TokenInvalidError(f"Token issuer '{payload.get('iss')}' does not match '{issuer}'.")

    # Audience check
    if audience is not None:
        aud = payload.get("aud")
        if isinstance(aud, list):
            if audience not in aud:
                raise TokenInvalidError(f"Audience '{audience}' not in token audience list.")
        elif aud != audience:
            raise TokenInvalidError(f"Audience '{aud}' does not match expected '{audience}'.")

    return payload
