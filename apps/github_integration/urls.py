"""URL configuration for GitHub integration endpoints and webhooks."""

from __future__ import annotations

from django.urls import path

from apps.github_integration.views import (
    GitHubSetupRedirectView,
    GitHubWebhookView,
    SiteGitHubAnalyzeView,
    SiteGitHubConnectionView,
    SiteGitHubConnectView,
    SiteGitHubIntegrationPRView,
    WorkspaceGitHubInstallationDetailView,
    WorkspaceGitHubInstallationListView,
    WorkspaceGitHubInstallationRepositoriesView,
)

app_name = "github_integration"

urlpatterns = [
    # Post-installation redirect from GitHub App (Setup URL)
    path("integrations/github/setup", GitHubSetupRedirectView.as_view(), name="github_setup"),
    path("integrations/github/setup/", GitHubSetupRedirectView.as_view()),
    # Inbound webhook ingestion (GH-6)
    path("webhooks/github/", GitHubWebhookView.as_view(), name="github_webhook"),
    # Workspace-level GitHub App installations (GH-1, GH-2)
    path(
        "workspaces/<uuid:workspace_id>/github/installations/",
        WorkspaceGitHubInstallationListView.as_view(),
        name="workspace_github_installation_list",
    ),
    path(
        "workspaces/<uuid:workspace_id>/github/installations/<int:installation_id>/",
        WorkspaceGitHubInstallationDetailView.as_view(),
        name="workspace_github_installation_detail",
    ),
    path(
        "workspaces/<uuid:workspace_id>/github/installations/<int:installation_id>/repositories/",
        WorkspaceGitHubInstallationRepositoriesView.as_view(),
        name="workspace_github_installation_repositories",
    ),
    # Site-level repository connections, framework analysis, and PR opening (GH-2, GH-3, GH-4, GH-5)
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/github/connection/",
        SiteGitHubConnectionView.as_view(),
        name="site_github_connection",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/github/connect/",
        SiteGitHubConnectView.as_view(),
        name="site_github_connect",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/github/analyze/",
        SiteGitHubAnalyzeView.as_view(),
        name="site_github_analyze",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/github/open-pr/",
        SiteGitHubIntegrationPRView.as_view(),
        name="site_github_open_pr",
    ),
]
