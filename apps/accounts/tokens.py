"""Token service providing JWT creation, rotation, and family-reuse detection."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone as dj_timezone

from apps.accounts.models import RefreshTokenFamily, User
from apps.common.jwt import (
    TokenExpiredError,
    TokenInvalidError,
    decode_jwt,
    encode_jwt,
)

logger = logging.getLogger("cms.security")


class TokenReuseDetectedError(TokenInvalidError):
    """Raised when an already-rotated refresh token is presented."""


def _get_jwt_secret() -> str:
    return str(getattr(settings, "JWT_SECRET_KEY", settings.SECRET_KEY))


def create_token_pair(user: User) -> dict[str, Any]:
    """Issue a new access token and a new refresh token family for the user."""
    now = int(time.time())
    access_lifetime = getattr(settings, "JWT_ACCESS_EXPIRATION_SECONDS", 900)  # 15 mins
    refresh_lifetime = getattr(settings, "JWT_REFRESH_EXPIRATION_SECONDS", 604800)  # 7 days

    family_id = uuid.uuid4()
    jti = uuid.uuid4()
    secret = _get_jwt_secret()
    issuer = getattr(settings, "JWT_ISSUER", "cms-backend")
    audience = getattr(settings, "JWT_AUDIENCE", "cms-api")

    expires_at = dj_timezone.now() + timedelta(seconds=refresh_lifetime)
    RefreshTokenFamily.objects.create(
        user=user,
        family_id=family_id,
        current_jti=jti,
        expires_at=expires_at,
    )

    access_payload = {
        "sub": str(user.id),
        "email": user.email,
        "type": "access",
        "jti": str(uuid.uuid4()),
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + access_lifetime,
    }

    refresh_payload = {
        "sub": str(user.id),
        "family_id": str(family_id),
        "jti": str(jti),
        "type": "refresh",
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + refresh_lifetime,
    }

    access_token = encode_jwt(access_payload, secret=secret)
    refresh_token = encode_jwt(refresh_payload, secret=secret)

    return {
        "access": access_token,
        "refresh": refresh_token,
        "token_type": "Bearer",  # nosec B105
        "expires_in": access_lifetime,
    }


def refresh_token_pair(refresh_token: str) -> dict[str, Any]:
    """Rotate the refresh token and return a new access + refresh pair.

    If an already-rotated token is submitted, the whole token family is revoked
    immediately to mitigate potential token theft.
    """
    secret = _get_jwt_secret()
    issuer = getattr(settings, "JWT_ISSUER", "cms-backend")
    audience = getattr(settings, "JWT_AUDIENCE", "cms-api")

    payload = decode_jwt(
        refresh_token,
        secret=secret,
        issuer=issuer,
        audience=audience,
    )

    if payload.get("type") != "refresh":
        raise TokenInvalidError("Provided token is not a refresh token.")

    user_id = payload.get("sub")
    family_id_str = payload.get("family_id")
    presented_jti_str = payload.get("jti")

    if not user_id or not family_id_str or not presented_jti_str:
        raise TokenInvalidError("Refresh token payload missing required claims.")

    try:
        family_id = uuid.UUID(family_id_str)
        presented_jti = uuid.UUID(presented_jti_str)
    except ValueError as exc:
        raise TokenInvalidError("Malformed token IDs.") from exc

    with transaction.atomic():
        family = (
            RefreshTokenFamily.objects.select_for_update()
            .filter(family_id=family_id, user_id=user_id)
            .first()
        )

        if family is None:
            raise TokenInvalidError("Token family does not exist.")

        if family.revoked:
            raise TokenInvalidError("Token family has already been revoked.")

        if family.expires_at < dj_timezone.now():
            raise TokenExpiredError("Refresh token family has expired.")

        # Family reuse detection
        if family.current_jti != presented_jti:
            family.revoked = True
            family.revoked_at = dj_timezone.now()
            family.save(update_fields=["revoked", "revoked_at", "updated_at"])
            is_reuse = True
        else:
            is_reuse = False
            # Issue new jti and rotate
            new_jti = uuid.uuid4()
            family.current_jti = new_jti
            family.save(update_fields=["current_jti", "updated_at"])

            user = family.user
            if not user.is_active:
                raise TokenInvalidError("User account is inactive.")

    if is_reuse:
        logger.warning(
            "Refresh token reuse detected for user=%s family=%s. Entire family revoked.",
            user_id,
            family_id,
        )
        raise TokenReuseDetectedError(
            "Refresh token reuse detected. The token family has been revoked for security."
        )

    now = int(time.time())
    access_lifetime = getattr(settings, "JWT_ACCESS_EXPIRATION_SECONDS", 900)
    # Remaining lifetime until family expiry
    remaining_refresh = max(60, int((family.expires_at - dj_timezone.now()).total_seconds()))

    access_payload = {
        "sub": str(user.id),
        "email": user.email,
        "type": "access",
        "jti": str(uuid.uuid4()),
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + access_lifetime,
    }

    new_refresh_payload = {
        "sub": str(user.id),
        "family_id": str(family.family_id),
        "jti": str(new_jti),
        "type": "refresh",
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + remaining_refresh,
    }

    return {
        "access": encode_jwt(access_payload, secret=secret),
        "refresh": encode_jwt(new_refresh_payload, secret=secret),
        "token_type": "Bearer",  # nosec B105
        "expires_in": access_lifetime,
    }


def revoke_token_family(refresh_token: str) -> None:
    """Revoke an active refresh token family (logout)."""
    secret = _get_jwt_secret()
    try:
        payload = decode_jwt(refresh_token, secret=secret)
    except TokenExpiredError:
        return
    except Exception as exc:
        raise TokenInvalidError("Invalid token.") from exc

    family_id_str = payload.get("family_id")
    if not family_id_str:
        return

    try:
        family_id = uuid.UUID(family_id_str)
    except ValueError:
        return

    RefreshTokenFamily.objects.filter(family_id=family_id).update(
        revoked=True,
        revoked_at=dj_timezone.now(),
        updated_at=dj_timezone.now(),
    )
