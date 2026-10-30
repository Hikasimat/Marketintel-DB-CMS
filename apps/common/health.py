"""Liveness and readiness probes (FND-2)."""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger("apps.common.health")


@extend_schema(exclude=True)
class LiveCheckView(APIView):
    """Liveness probe: verifies process is alive and accepting requests."""

    permission_classes = (permissions.AllowAny,)
    authentication_classes = ()
    throttle_classes = ()

    def get(self, request, *args, **kwargs) -> Response:
        return Response({"status": "live"}, status=status.HTTP_200_OK)


@extend_schema(exclude=True)
class ReadyCheckView(APIView):
    """Readiness probe: verifies essential dependencies (PostgreSQL, Redis)."""

    permission_classes = (permissions.AllowAny,)
    authentication_classes = ()
    throttle_classes = ()

    def get(self, request, *args, **kwargs) -> Response:
        errors: list[str] = []

        # 1. Database check
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                cursor.fetchone()
        except Exception as exc:
            logger.error("Readiness check failed for database: %s", exc)
            errors.append("database")

        # 2. Redis cache check if configured
        redis_url = getattr(settings, "REDIS_URL", None)
        if redis_url and getattr(settings, "SETTINGS_PROFILE", "") != "test":
            try:
                from django.core.cache import cache

                cache.set("health_check_ping", "pong", timeout=5)
                if cache.get("health_check_ping") != "pong":
                    raise ValueError("Redis cache readback mismatch")
            except Exception as exc:
                logger.error("Readiness check failed for cache/redis: %s", exc)
                errors.append("cache")

        if errors:
            # Generic error response without leaking internal connection or stack details
            return Response(
                {"status": "not_ready", "unhealthy": errors},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response({"status": "ready"}, status=status.HTTP_200_OK)
