"""URL patterns for analytics management, public configuration, and event ingestion."""

from django.urls import path

from apps.analytics.views import (
    FirstPartyOverviewReportView,
    GA4AuthorizeView,
    GA4CallbackView,
    GA4ConnectionView,
    GA4DisconnectView,
    GA4PropertiesListView,
    GA4PropertySelectView,
    GA4ReportView,
    GoogleTagSnippetView,
    PublicAnalyticsConfigView,
    PublicEventIngestView,
    SiteAnalyticsConfigView,
    VisitorDataErasureView,
)

app_name = "analytics"

urlpatterns = [
    # Google Tag (gtag.js) Snippet Generator with Consent Mode v2
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/analytics/tag/",
        GoogleTagSnippetView.as_view(),
        name="tag_snippet",
    ),
    # GA4 OAuth 2.0 Authorization Code Flow
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/analytics/google/authorize/",
        GA4AuthorizeView.as_view(),
        name="ga4_authorize",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/analytics/google/callback/",
        GA4CallbackView.as_view(),
        name="ga4_callback",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/analytics/google/disconnect/",
        GA4DisconnectView.as_view(),
        name="ga4_disconnect",
    ),
    # GA4 Properties and Streams Discovery
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/analytics/properties/",
        GA4PropertiesListView.as_view(),
        name="ga4_properties",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/analytics/properties/select/",
        GA4PropertySelectView.as_view(),
        name="ga4_property_select",
    ),
    # Analytics Configuration & GA4 Connection
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
    # GA4 Reports (overview, acquisition, pages, audience, events, realtime)
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/analytics/reports/ga4/",
        GA4ReportView.as_view(),
        name="ga4_reports",
    ),
    # First-Party privacy-preserving metrics & GDPR erasure
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
        "public/sites/<slug:site_slug>/analytics-config/",
        PublicAnalyticsConfigView.as_view(),
    ),
    path(
        "public/sites/<slug:site_slug>/events",
        PublicEventIngestView.as_view(),
        name="public_ingest",
    ),
    path(
        "public/sites/<slug:site_slug>/events/",
        PublicEventIngestView.as_view(),
    ),
    path(
        "public/sites/<slug:site_slug>/analytics/events",
        PublicEventIngestView.as_view(),
    ),
    path(
        "public/sites/<slug:site_slug>/analytics/events/",
        PublicEventIngestView.as_view(),
    ),
]
