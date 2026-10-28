"""Tests for unsupported framework detection and manual integration fallback (GH-5)."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status

from apps.github_integration.analyzer import analyze_repository_manifests
from apps.github_integration.models import (
    DetectedFramework,
    IntegrationStatus,
    SiteGitHubRepoConnection,
)

pytestmark = pytest.mark.django_db


def test_missing_manifest_returns_unsupported():
    """Repositories lacking package.json return UNSUPPORTED with manual integration guide."""
    res = analyze_repository_manifests({})
    assert res["detected_framework"] == DetectedFramework.UNSUPPORTED
    assert res["confidence"] == "NONE"
    assert res["manual_integration_required"] is True
    assert "manual-integration" in res["integration_guide_url"]


def test_custom_or_backend_dependencies_return_unsupported():
    """Repositories with backend-only or unsupported frontends return clear manual state."""
    files = {
        "package.json": (
            '{"name": "backend-service", "dependencies": {"express": "^4.18.0", "pg": "^8.11.0"}}'
        )
    }
    res = analyze_repository_manifests(files)
    assert res["detected_framework"] == DetectedFramework.UNSUPPORTED
    assert res["confidence"] == "NONE"
    assert res["manual_integration_required"] is True
    assert "manual-integration" in res["integration_guide_url"]


def test_api_analyze_unsupported_framework_endpoint(github_setup, settings):
    """The /analyze/ endpoint sets connection status to ANALYZED with UNSUPPORTED framework."""
    settings.GITHUB_APP_ENABLED = True
    client = github_setup["client"]
    editor = github_setup["editor"]
    workspace = github_setup["workspace"]
    site = github_setup["site"]
    installation = github_setup["installation"]

    # Connect to custom-service (which only has express in mock client)
    connection = SiteGitHubRepoConnection.objects.create(
        site=site,
        installation=installation,
        repo_full_name="acme-corp/custom-service",
        selected_branch="master",
        integration_status=IntegrationStatus.CONNECTED,
    )

    client.force_authenticate(user=editor)
    analyze_url = reverse(
        "github_integration:site_github_analyze",
        kwargs={"workspace_id": workspace.id, "site_id": site.id},
    )

    resp = client.post(analyze_url)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["detected_framework"] == DetectedFramework.UNSUPPORTED
    assert resp.data["manual_integration_required"] is True

    connection.refresh_from_db()
    assert connection.detected_framework == DetectedFramework.UNSUPPORTED
    assert connection.integration_status == IntegrationStatus.ANALYZED
