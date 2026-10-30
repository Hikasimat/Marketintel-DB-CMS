"""Serializers for authentication and user accounts."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

from django.contrib.auth import authenticate
from rest_framework import serializers

from apps.accounts.models import User

logger = logging.getLogger("cms.auth")


_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _verify_with_market_intel_endpoint(identifier: str, password: str) -> dict[str, Any] | None:
    """Verify credentials against Market Intel DB project login endpoints.

    Authenticates existing users via Market Intel DB's CookieTokenObtainPairView
    (/api/auth/login/) and retrieves user details from /api/auth/me/.
    """
    from django.conf import settings

    if getattr(settings, "SETTINGS_PROFILE", "") == "test" or os.getenv(
        "DJANGO_SETTINGS_MODULE", ""
    ).endswith(".test"):
        return None

    raw_env_url = os.getenv("MARKET_INTEL_LOGIN_URL")
    endpoints = []
    if raw_env_url:
        endpoints.append(raw_env_url.strip())
    endpoints.extend(
        [
            "https://marketintel.hikasimat.com/api/auth/login/",
            "http://127.0.0.1:8000/api/auth/login/",
            "http://localhost:8000/api/auth/login/",
        ]
    )

    payload = json.dumps(
        {"email": identifier, "username": identifier, "password": password}
    ).encode("utf-8")
    for endpoint in endpoints:
        if not endpoint:
            continue
        try:
            req = urllib.request.Request(  # noqa: S310
                endpoint,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": _BROWSER_USER_AGENT,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as response:  # nosec B310 # noqa: S310
                if response.status == 200:
                    resp_data = json.loads(response.read().decode())
                    access_token = resp_data.get("access")
                    if access_token:
                        logger.info(
                            "Market Intel DB authenticated user: %s via %s", identifier, endpoint
                        )
                        # Fetch identity & roles from /api/auth/me/
                        base_api = endpoint.split("/api/auth/login/")[0]
                        me_endpoint = f"{base_api}/api/auth/me/"
                        me_data: dict[str, Any] = {}
                        try:
                            me_req = urllib.request.Request(  # noqa: S310
                                me_endpoint,
                                headers={
                                    "Authorization": f"Bearer {access_token}",
                                    "User-Agent": _BROWSER_USER_AGENT,
                                },
                                method="GET",
                            )
                            with urllib.request.urlopen(me_req, timeout=4) as me_resp:  # nosec B310 # noqa: S310
                                if me_resp.status == 200:
                                    me_data = json.loads(me_resp.read().decode())
                        except Exception as exc:
                            logger.debug("Could not fetch Market Intel profile: %s", exc)

                        return {
                            "email": me_data.get("email") or identifier,
                            "username": me_data.get("username") or identifier,
                            "role": me_data.get("role", "PRE"),
                            "is_superuser": bool(me_data.get("is_superuser", False)),
                            "first_name": me_data.get("first_name", ""),
                            "last_name": me_data.get("last_name", ""),
                        }
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 401):
                logger.warning("Market Intel DB rejected credentials for %s: %s", identifier, exc)
                return None
            logger.debug("Market Intel DB endpoint returned %s: %s", exc.code, endpoint)
        except Exception as exc:
            logger.debug("Could not reach Market Intel DB endpoint %s: %s", endpoint, exc)
    return None


def _verify_with_market_intel_database(identifier: str, password: str) -> dict[str, Any] | None:
    """Verify credentials directly against public.auth_user in shared PostgreSQL database."""
    from django.conf import settings
    from django.contrib.auth.hashers import check_password
    from django.db import connection

    if getattr(settings, "SETTINGS_PROFILE", "") == "test" or os.getenv(
        "DJANGO_SETTINGS_MODULE", ""
    ).endswith(".test"):
        return None

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, username, email, password, is_active, is_superuser, is_staff "
                "FROM public.auth_user "
                "WHERE LOWER(email) = LOWER(%s) OR LOWER(username) = LOWER(%s) "
                "LIMIT 1;",
                [identifier, identifier],
            )
            row = cursor.fetchone()
            if not row:
                return None
            _, username, email, hashed_password, is_active, is_superuser, is_staff = row
            if not is_active:
                return None
            if check_password(password, hashed_password):
                logger.info("Market Intel DB authenticated user via direct DB: %s", identifier)
                return {
                    "email": email or identifier,
                    "username": username or identifier,
                    "role": "ADM" if is_superuser else "PRE",
                    "is_superuser": bool(is_superuser),
                    "is_staff": bool(is_staff),
                }
    except Exception as exc:
        logger.debug("Database auth fallback skipped: %s", exc)
    return None


class LoginSerializer(serializers.Serializer[Any]):
    email = serializers.CharField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        identifier = attrs.get("email", "").strip()
        email = identifier.lower() if "@" in identifier else identifier
        password = attrs.get("password", "")

        # 1. Primary authentication via Market Intel DB HTTP endpoint
        market_intel_user = _verify_with_market_intel_endpoint(identifier, password)

        # 1.5 Fallback to shared PostgreSQL database authentication
        if not market_intel_user:
            market_intel_user = _verify_with_market_intel_database(identifier, password)

        if market_intel_user:
            resolved_email = (market_intel_user.get("email") or email).lower().strip()
            is_super = market_intel_user.get("is_superuser", False)
            role = market_intel_user.get("role", "PRE")
            is_staff = is_super or role in ("ADM", "MANAGER")

            user, _ = User.objects.get_or_create(
                email=resolved_email,
                defaults={"is_active": True, "is_staff": is_staff},
            )
            if not user.is_active or user.is_staff != is_staff:
                user.is_active = True
                user.is_staff = is_staff
                user.save(update_fields=["is_active", "is_staff"])

            # Ensure user is enrolled into primary workspace
            try:
                from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole

                workspace = Workspace.objects.first()
                if not workspace:
                    workspace = Workspace.objects.create(name="Default Workspace", slug="default")

                assigned_role = (
                    WorkspaceRole.OWNER
                    if is_super
                    else (
                        WorkspaceRole.ADMIN if role in ("ADM", "MANAGER") else WorkspaceRole.EDITOR
                    )
                )
                membership, created = WorkspaceMembership.objects.get_or_create(
                    workspace=workspace,
                    user=user,
                    defaults={"role": assigned_role},
                )
                if not created and membership.role != assigned_role and is_super:
                    membership.role = WorkspaceRole.OWNER
                    membership.save(update_fields=["role"])
            except Exception as e:
                logger.warning("Could not link user to workspace: %s", e)

            attrs["user"] = user
            return attrs

        # 2. Local fallback verification
        authenticated_user = authenticate(email=email, password=password)
        local_user: User | None = (
            authenticated_user if isinstance(authenticated_user, User) else None
        )
        if not local_user:
            try:
                candidate = User.objects.get(email=email)
                if candidate.check_password(password):
                    local_user = candidate
            except User.DoesNotExist:
                local_user = None

        if not local_user or not local_user.is_active:
            raise serializers.ValidationError("Invalid credentials or account inactive.")

        attrs["user"] = local_user
        return attrs


class TokenRefreshSerializer(serializers.Serializer[Any]):
    refresh = serializers.CharField()


class LogoutSerializer(serializers.Serializer[Any]):
    refresh = serializers.CharField()


class UserSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = ("id", "email", "is_active", "is_staff", "created_at")
        read_only_fields = fields
