"""URL configuration for CMS backend."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpResponse
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.common.console import testing_console_view
from apps.common.health import LiveCheckView, ReadyCheckView

urlpatterns = [
    # Favicon 204
    path("favicon.ico", lambda r: HttpResponse(status=204)),
    # Interactive Developer & QA Testing Console
    path("console/", testing_console_view, name="testing_console"),
    path("", RedirectView.as_view(url="/console/", permanent=False)),
    # Health and readiness probes (unauthenticated, exempted from HTTPS redirect)
    path("health/live", LiveCheckView.as_view(), name="health_live"),
    path("health/ready", ReadyCheckView.as_view(), name="health_ready"),
    # OpenAPI v3 schema definition
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    # Core domain API routes
    path("api/v1/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.tenancy.urls")),
    path("api/v1/", include("apps.audit.urls")),
    path("api/v1/", include("apps.sites.urls")),
    path("api/v1/", include("apps.content.urls")),
    path("api/v1/", include("apps.seo.urls")),
    path("api/v1/", include("apps.integrations.urls")),
    path("api/v1/", include("apps.analytics.urls")),
    path("api/v1/", include("apps.consent.urls")),
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
