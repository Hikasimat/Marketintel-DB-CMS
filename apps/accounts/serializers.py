"""Serializers for authentication and user accounts."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings
from django.contrib.auth import authenticate
from django.core.cache import cache
from rest_framework import serializers

from apps.accounts.models import User

logger = logging.getLogger("cms.auth")


_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def verify_market_intel_token(access_token: str) -> dict[str, Any] | None:
    """Verify an external Market Intel access token against Market Intel's /api/auth/me/.

    Enforces that the user is an active registered Market Intel user.
    Uses short-term in-memory cache to prevent redundant HTTP roundtrips.
    """
    if not access_token or not access_token.strip():
        return None

    clean_token = access_token.strip()

    if getattr(settings, "SETTINGS_PROFILE", "") == "test" or os.getenv(
        "DJANGO_SETTINGS_MODULE", ""
    ).endswith(".test"):
        if clean_token.startswith("mock-valid-marketintel-token-"):
            user_part = clean_token.replace("mock-valid-marketintel-token-", "")
            return {
                "email": f"{user_part}@marketintel.internal",
                "username": user_part,
                "role": "ADM" if "admin" in user_part else "PRE",
                "is_superuser": "admin" in user_part,
                "is_active": True,
            }
        return None

    cache_key = f"mi_token_verify_{hashlib.sha256(clean_token.encode('utf-8')).hexdigest()}"
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        return cached_data

    raw_env_url = os.getenv("MARKET_INTEL_ME_URL") or os.getenv("MARKET_INTEL_BACKEND_URL")
    endpoints = []
    if raw_env_url:
        clean = raw_env_url.strip().rstrip("/")
        endpoints.append(f"{clean}/api/auth/me/" if not clean.endswith("/me/") else clean)
    endpoints.extend(
        [
            "https://marketintel.hikasimat.com/api/auth/me/",
            "https://marketinteldbapp.hikasimat.com/api/auth/me/",
            "http://127.0.0.1:8000/api/auth/me/",
            "http://localhost:8000/api/auth/me/",
        ]
    )

    for endpoint in endpoints:
        if not endpoint:
            continue
        try:
            req = urllib.request.Request(  # noqa: S310
                endpoint,
                headers={
                    "Authorization": f"Bearer {clean_token}",
                    "User-Agent": _BROWSER_USER_AGENT,
                    "Accept": "application/json",
                },
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:  # nosec B310 # noqa: S310
                if resp.status == 200:
                    raw_body = resp.read().decode()
                    try:
                        data = json.loads(raw_body)
                    except Exception as json_err:
                        logger.debug("Non-JSON response from endpoint %s: %s", endpoint, json_err)
                        continue
                    if not isinstance(data, dict):
                        continue
                    if data.get("is_active", True) is False:
                        logger.warning("Market Intel account %s is inactive.", data.get("email"))
                        return None
                    result = {
                        "email": (data.get("email") or data.get("username") or "").lower().strip(),
                        "username": data.get("username", ""),
                        "role": data.get("role", "PRE"),
                        "is_superuser": bool(data.get("is_superuser", False)),
                        "first_name": data.get("first_name", ""),
                        "last_name": data.get("last_name", ""),
                    }
                    if not result["email"]:
                        continue
                    cache.set(cache_key, result, timeout=60)
                    return result
        except urllib.error.HTTPError as exc:
            logger.debug("Market Intel endpoint %s returned HTTP %s: %s", endpoint, exc.code, exc)
            continue
        except Exception as exc:
            logger.debug("Could not reach Market Intel me endpoint %s: %s", endpoint, exc)
            continue

    return None


def _ensure_workspace_enrollment(user: User, market_intel_user: dict[str, Any]) -> None:
    """Enroll user into default workspace with appropriate role based on Market Intel profile."""
    try:
        from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole

        workspace = Workspace.objects.first()
        if not workspace:
            workspace = Workspace.objects.create(name="Default Workspace", slug="default")

        is_super = market_intel_user.get("is_superuser", False)
        role = market_intel_user.get("role", "PRE")
        assigned_role = (
            WorkspaceRole.OWNER
            if is_super
            else (WorkspaceRole.ADMIN if role in ("ADM", "MANAGER") else WorkspaceRole.EDITOR)
        )
        membership, created = WorkspaceMembership.objects.get_or_create(
            workspace=workspace,
            user=user,
            defaults={"role": assigned_role},
        )
        if not created and membership.role != assigned_role and is_super:
            membership.role = WorkspaceRole.OWNER
            membership.save(update_fields=["role"])
    except Exception as exc:
        logger.warning("Could not link user to workspace: %s", exc)


def _verify_with_market_intel_endpoint(identifier: str, password: str) -> dict[str, Any] | None:
    """Verify credentials against Market Intel DB project login endpoints.

    Authenticates existing users via Market Intel DB's CookieTokenObtainPairView
    (/api/auth/login/) and retrieves user details from /api/auth/me/.
    """
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
            "https://marketinteldbapp.hikasimat.com/api/auth/login/",
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


class LoginSerializer(serializers.Serializer[Any]):
    email = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        style={"input_type": "password"},
    )
    token = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Optional Market Intel JWT access token for direct token-based authentication.",
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        token = attrs.get("token", "").strip()
        identifier = attrs.get("email", "").strip()
        email = identifier.lower() if "@" in identifier else identifier
        password = attrs.get("password", "")

        market_intel_user: dict[str, Any] | None = None

        # 1. Direct Market Intel token authentication
        if token:
            market_intel_user = verify_market_intel_token(token)
            if not market_intel_user:
                raise serializers.ValidationError("Invalid or expired Market Intel access token.")

        # 2. Market Intel credential authentication
        if not market_intel_user and identifier and password:
            market_intel_user = _verify_with_market_intel_endpoint(identifier, password)

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

            _ensure_workspace_enrollment(user, market_intel_user)
            attrs["user"] = user
            return attrs

        # 3. Local fallback verification (for standalone CMS tests/dev)
        if not email or not password:
            raise serializers.ValidationError(
                "Must provide either a valid Market Intel token or email and password."
            )

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


class MarketIntelTokenExchangeSerializer(serializers.Serializer[Any]):
    token = serializers.CharField(
        help_text="Market Intel access token obtained via Market Intel OAuth or login."
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        raw_token = attrs.get("token", "").strip()
        market_intel_user = verify_market_intel_token(raw_token)
        if not market_intel_user:
            raise serializers.ValidationError("Invalid or expired Market Intel access token.")

        resolved_email = market_intel_user["email"]
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

        _ensure_workspace_enrollment(user, market_intel_user)
        attrs["user"] = user
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
