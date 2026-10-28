"""Tests for safe repository and branch selection (GH-2)."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status

from apps.audit.models import AuditEvent
from apps.github_integration.models import IntegrationStatus, SiteGitHubRepoConnection

pytestmark = pytest.mark.django_db


def test_list_installation_repositories(github_setup, settings):
    """Authenticated workspace member can list accessible repositories."""
    settings.GITHUB_APP_ENABLED = True
    client = github_setup["client"]
    editor = github_setup["editor"]
    workspace = github_setup["workspace"]
    installation = github_setup["installation"]

    client.force_authenticate(user=editor)
    repos_url = reverse(
        "github_integration:workspace_github_installation_repositories",
        kwargs={"workspace_id": workspace.id, "installation_id": installation.installation_id},
    )
    resp = client.get(repos_url)
    assert resp.status_code == status.HTTP_200_OK
    assert "repositories" in resp.data
    repo_names = [r["full_name"] for r in resp.data["repositories"]]
    assert "acme-corp/nextjs-frontend" in repo_names
    assert "acme-corp/vite-blog" in repo_names


def test_connect_repository_valid(github_setup, settings):
    """Workspace admin can connect an authorized repo and branch to a site."""
    settings.GITHUB_APP_ENABLED = True
    client = github_setup["client"]
    owner = github_setup["owner"]
    workspace = github_setup["workspace"]
    site = github_setup["site"]
    installation = github_setup["installation"]

    client.force_authenticate(user=owner)
    connect_url = reverse(
        "github_integration:site_github_connect",
        kwargs={"workspace_id": workspace.id, "site_id": site.id},
    )

    payload = {
        "installation_id": installation.installation_id,
        "repo_full_name": "acme-corp/nextjs-frontend",
        "selected_branch": "main",
    }
    resp = client.post(connect_url, payload, format="json")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["repo_full_name"] == "acme-corp/nextjs-frontend"
    assert resp.data["selected_branch"] == "main"
    assert resp.data["integration_status"] == IntegrationStatus.CONNECTED

    connection = SiteGitHubRepoConnection.objects.get(site=site)
    assert connection.repo_full_name == "acme-corp/nextjs-frontend"

    audit = AuditEvent.objects.filter(action="GITHUB_REPO_CONNECTED").first()
    assert audit is not None
    assert audit.payload["repo_full_name"] == "acme-corp/nextjs-frontend"


@pytest.mark.parametrize(
    "malicious_repo",
    [
        "invalid_slug",
        "owner/repo/extra",
        "owner/repo;rm -rf",
        "../traversal/repo",
        "owner/repo\0null",
    ],
)
def test_connect_repository_malicious_slugs_rejected(malicious_repo, github_setup, settings):
    """Malicious or invalid repository slugs are rejected with HTTP 400."""
    settings.GITHUB_APP_ENABLED = True
    client = github_setup["client"]
    owner = github_setup["owner"]
    workspace = github_setup["workspace"]
    site = github_setup["site"]
    installation = github_setup["installation"]

    client.force_authenticate(user=owner)
    connect_url = reverse(
        "github_integration:site_github_connect",
        kwargs={"workspace_id": workspace.id, "site_id": site.id},
    )
    payload = {
        "installation_id": installation.installation_id,
        "repo_full_name": malicious_repo,
        "selected_branch": "main",
    }
    resp = client.post(connect_url, payload, format="json")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.parametrize(
    "malicious_branch",
    [
        "main..feature",
        "branch~1",
        "branch^2",
        "branch@{1}",
        "branch with spaces",
        "branch:bad",
        "branch?wild",
        "-starts-with-dash",
        "branch.lock",
    ],
)
def test_connect_repository_malicious_branch_rejected(malicious_branch, github_setup, settings):
    """Malicious git branch revision metacharacters are rejected with HTTP 400."""
    settings.GITHUB_APP_ENABLED = True
    client = github_setup["client"]
    owner = github_setup["owner"]
    workspace = github_setup["workspace"]
    site = github_setup["site"]
    installation = github_setup["installation"]

    client.force_authenticate(user=owner)
    connect_url = reverse(
        "github_integration:site_github_connect",
        kwargs={"workspace_id": workspace.id, "site_id": site.id},
    )
    payload = {
        "installation_id": installation.installation_id,
        "repo_full_name": "acme-corp/nextjs-frontend",
        "selected_branch": malicious_branch,
    }
    resp = client.post(connect_url, payload, format="json")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


def test_connect_repository_non_existent_branch_rejected(github_setup, settings):
    """Connecting to a branch that does not exist in the repository returns HTTP 400."""
    settings.GITHUB_APP_ENABLED = True
    client = github_setup["client"]
    owner = github_setup["owner"]
    workspace = github_setup["workspace"]
    site = github_setup["site"]
    installation = github_setup["installation"]

    client.force_authenticate(user=owner)
    connect_url = reverse(
        "github_integration:site_github_connect",
        kwargs={"workspace_id": workspace.id, "site_id": site.id},
    )
    payload = {
        "installation_id": installation.installation_id,
        "repo_full_name": "acme-corp/nextjs-frontend",
        "selected_branch": "non-existent-branch",
    }
    resp = client.post(connect_url, payload, format="json")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "not found" in str(resp.data).lower()
