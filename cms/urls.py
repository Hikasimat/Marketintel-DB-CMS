"""URL configuration for CMS backend."""

from __future__ import annotations

from django.conf import settings
from django.urls import path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.common.health import LiveCheckView, ReadyCheckView

urlpatterns = [
    # Health and readiness probes (unauthenticated, exempted from HTTPS redirect)
    path("health/live", LiveCheckView.as_view(), name="health_live"),
    path("health/ready", ReadyCheckView.as_view(), name="health_ready"),
    # OpenAPI v3 schema definition
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
]

# Interactive API documentation (enabled only in non-production or when explicitly configured)
if getattr(settings, "API_DOCS_ENABLED", False):
    urlpatterns += [
        path(
            "api/v1/docs/",
            SpectacularSwaggerView.as_view(url_name="schema"),
            name="swagger-ui",
        ),
        path(
            "api/v1/redoc/",
            SpectacularRedocView.as_view(url_name="schema"),
            name="redoc",
        ),
    ]

# Optional Django admin interface
if getattr(settings, "ADMIN_ENABLED", False):
    from django.contrib import admin

    urlpatterns.append(path("admin/", admin.site.urls))
