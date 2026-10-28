"""URL patterns for analytics management, public configuration, and event ingestion."""

from django.urls import path

from apps.analytics.views import (
    FirstPartyOverviewReportView,
    GA4ConnectionView,
    GA4ReportView,
    PublicAnalyticsConfigView,
    PublicEventIngestView,
    SiteAnalyticsConfigView,
    VisitorDataErasureView,
)

app_name = "analytics"

urlpatterns = [
    # Management endpoints
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/analytics/config/",
        SiteAnalyticsConfigView.as_view(),
        name="config",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/analytics/ga4/",
        GA4ConnectionView.as_view(),
        name="ga4_connection",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/analytics/reports/ga4/",
        GA4ReportView.as_view(),
        name="ga4_reports",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/analytics/first-party/overview/",
        FirstPartyOverviewReportView.as_view(),
        name="first_party_overview",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/analytics/first-party/visitors/<str:visitor_id>/",
        VisitorDataErasureView.as_view(),
        name="visitor_erasure",
    ),
    # Public endpoints
    path(
        "public/sites/<slug:site_slug>/analytics-config",
        PublicAnalyticsConfigView.as_view(),
        name="public_config",
    ),
    path(
        "public/sites/<slug:site_slug>/events",
        PublicEventIngestView.as_view(),
        name="public_ingest",
    ),
]
