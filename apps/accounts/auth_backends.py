"""Authentication backends for internal JWTs and external identity issuers."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

from apps.accounts.models import User
from apps.common.jwt import (
    TokenExpiredError,
    TokenInvalidError,
    decode_jwt,
)

logger = logging.getLogger("cms.auth")


class JWTAuthentication(authentication.BaseAuthentication):
    """Authenticates API requests using internal HS256 Bearer JWTs."""

    keyword = "Bearer"

    def authenticate(self, request: Request) -> tuple[User, dict[str, Any]] | None:
        auth_header = authentication.get_authorization_header(request).decode("utf-8")
        if not auth_header:
            return None

        parts = auth_header.split()
        if len(parts) != 2 or parts[0] != self.keyword:
            return None

        raw_token = parts[1]
        secret = str(getattr(settings, "JWT_SECRET_KEY", settings.SECRET_KEY))
        issuer = getattr(settings, "JWT_ISSUER", "cms-backend")
        audience = getattr(settings, "JWT_AUDIENCE", "cms-api")

        try:
            payload = decode_jwt(
                raw_token,
                secret=secret,
                issuer=issuer,
                audience=audience,
            )
        except TokenExpiredError as exc:
            raise AuthenticationFailed(
                {"code": "token_expired", "message": "Access token has expired."}
            ) from exc
        except TokenInvalidError:
            # Token is not a valid internal JWT; return None so other backends can try
            return None

        if payload.get("type") != "access":
            raise AuthenticationFailed(
                {"code": "token_invalid", "message": "Expected an access token."}
            )

        user_id = payload.get("sub")
        if not user_id:
            raise AuthenticationFailed(
                {"code": "token_invalid", "message": "Token missing subject claim."}
            )

        try:
            user = User.objects.get(id=user_id, is_active=True)
        except User.DoesNotExist as exc:
            raise AuthenticationFailed(
                {"code": "user_inactive_or_missing", "message": "User not found or inactive."}
            ) from exc

        return (user, payload)

    def authenticate_header(self, request: Request) -> str:
        return self.keyword


class ExternalIssuerAuthentication(authentication.BaseAuthentication):
    """Validates external IdP tokens (AUTH-5 boundary adapter).

    Decoupled from internal models of external providers. Configured via
    EXTERNAL_AUTH_ISSUERS dictionary in settings.
    """

    keyword = "Bearer"

    def authenticate(self, request: Request) -> tuple[User, dict[str, Any]] | None:
        auth_header = authentication.get_authorization_header(request).decode("utf-8")
        if not auth_header:
            return None

        parts = auth_header.split()
        if len(parts) != 2 or parts[0] != self.keyword:
            return None

        raw_token = parts[1]
        external_issuers = getattr(settings, "EXTERNAL_AUTH_ISSUERS", {})
        if not external_issuers:
            return None

        # Inspect unverified header to see issuer or try configured issuers
        for _iss_name, config in external_issuers.items():
            secret = config.get("secret")
            if not secret:
                continue
            expected_issuer = config.get("issuer")
            expected_audience = config.get("audience")

            try:
                payload = decode_jwt(
                    raw_token,
                    secret=secret,
                    issuer=expected_issuer,
                    audience=expected_audience,
                )
            except (TokenExpiredError, TokenInvalidError):
                continue

            email = payload.get("email")
            if not email:
                raise AuthenticationFailed(
                    {"code": "external_auth_error", "message": "External token missing email."}
                )

            # Resolve or provision local shadow user without MarketIntel DB coupling
            user, _ = User.objects.get_or_create(
                email=email.lower(),
                defaults={"is_active": True},
            )
            return (user, payload)

        return None

    def authenticate_header(self, request: Request) -> str:
        return self.keyword


try:
    from drf_spectacular.extensions import OpenApiAuthenticationExtension

    class JWTAuthenticationScheme(OpenApiAuthenticationExtension):
        target_class = "apps.accounts.auth_backends.JWTAuthentication"
        name = "jwtAuth"

        def get_security_definition(self, auto_schema: Any) -> dict[str, Any]:
            return {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
            }

    class ExternalIssuerAuthenticationScheme(OpenApiAuthenticationExtension):
        target_class = "apps.accounts.auth_backends.ExternalIssuerAuthentication"
        name = "externalBearerAuth"

        def get_security_definition(self, auto_schema: Any) -> dict[str, Any]:
            return {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
            }
except ImportError:
    pass
