"""URL routing for audit trail inspection."""

from django.urls import path

from apps.audit.views import WorkspaceAuditLogListView

app_name = "audit"

urlpatterns = [
    path(
        "workspaces/<uuid:workspace_id>/audit-logs/",
        WorkspaceAuditLogListView.as_view(),
        name="workspace_audit_logs",
    ),
]
