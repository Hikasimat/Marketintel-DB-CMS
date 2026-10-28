"""URL patterns for search engine integrations and IndexNow verification."""

from django.urls import path, re_path

from apps.integrations.views import (
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
    # Management endpoints
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
