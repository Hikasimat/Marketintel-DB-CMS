"""URL patterns for search engine integrations and IndexNow verification."""

from django.urls import path, re_path

from apps.integrations.views import (
    GoogleSearchConsoleAnalyticsView,
    GoogleSearchConsoleAuthorizeView,
    GoogleSearchConsoleCallbackView,
    GoogleSearchConsoleDisconnectView,
    GoogleSearchConsolePropertiesView,
    GoogleSearchConsolePropertySelectView,
    GoogleSearchConsoleSitemapsView,
    IndexNowKeyView,
    IndexSubmissionLogListView,
    ManualSubmissionView,
    PublicIndexNowKeyFileView,
    SearchConnectionDetailView,
    SearchConnectionListCreateView,
    UrlInspectionView,
)

app_name = "integrations"

urlpatterns = [
    # Google Search Console OAuth & Management
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/integrations/google/authorize/",
        GoogleSearchConsoleAuthorizeView.as_view(),
        name="gsc_authorize",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/integrations/google/callback/",
        GoogleSearchConsoleCallbackView.as_view(),
        name="gsc_callback",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/integrations/google/disconnect/",
        GoogleSearchConsoleDisconnectView.as_view(),
        name="gsc_disconnect",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/integrations/google/properties/",
        GoogleSearchConsolePropertiesView.as_view(),
        name="gsc_properties",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/integrations/google/properties/select/",
        GoogleSearchConsolePropertySelectView.as_view(),
        name="gsc_property_select",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/integrations/google/search-analytics/",
        GoogleSearchConsoleAnalyticsView.as_view(),
        name="gsc_analytics",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/integrations/google/sitemaps/",
        GoogleSearchConsoleSitemapsView.as_view(),
        name="gsc_sitemaps",
    ),
    # Existing search engine connections
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/integrations/connections/",
        SearchConnectionListCreateView.as_view(),
        name="connection_list_create",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/integrations/connections/<uuid:connection_id>/",
        SearchConnectionDetailView.as_view(),
        name="connection_detail",
    ),
    # IndexNow keys and rotation
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/integrations/indexnow/",
        IndexNowKeyView.as_view(),
        name="indexnow_key",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/integrations/indexnow/rotate/",
        IndexNowKeyView.as_view(),
        name="indexnow_rotate",
    ),
    # Submission logs and URL Inspection
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/integrations/logs/",
        IndexSubmissionLogListView.as_view(),
        name="submission_log_list",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/integrations/submit/",
        ManualSubmissionView.as_view(),
        name="manual_submission",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/integrations/inspect-url/",
        UrlInspectionView.as_view(),
        name="inspect_url",
    ),
    # Public IndexNow key verification file (must end in .txt)
    re_path(
        r"^public/sites/(?P<site_slug>[-a-zA-Z0-9_]+)/(?P<key_file>[^/]+\.txt)$",
        PublicIndexNowKeyFileView.as_view(),
        name="public_indexnow_key",
    ),
]
