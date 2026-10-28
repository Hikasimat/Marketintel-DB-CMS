"""URL routing for workspaces and memberships."""

from django.urls import path

from apps.tenancy.views import (
    WorkspaceDetailView,
    WorkspaceListCreateView,
    WorkspaceMemberDetailView,
    WorkspaceMemberListCreateView,
)

app_name = "tenancy"

urlpatterns = [
    path("workspaces/", WorkspaceListCreateView.as_view(), name="workspace_list_create"),
    path("workspaces/<uuid:workspace_id>/", WorkspaceDetailView.as_view(), name="workspace_detail"),
    path(
        "workspaces/<uuid:workspace_id>/members/",
        WorkspaceMemberListCreateView.as_view(),
        name="workspace_member_list_create",
    ),
    path(
        "workspaces/<uuid:workspace_id>/members/<uuid:member_id>/",
        WorkspaceMemberDetailView.as_view(),
        name="workspace_member_detail",
    ),
]
