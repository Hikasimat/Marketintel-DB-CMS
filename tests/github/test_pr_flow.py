"""Tests for safe branch and Pull Request workflow (GH-4)."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status

from apps.audit.models import AuditEvent
from apps.github_integration.analyzer import generate_integration_patch_files
from apps.github_integration.models import (
    DetectedFramework,
    IntegrationStatus,
    SiteGitHubRepoConnection,
)

pytestmark = pytest.mark.django_db


def test_generate_integration_patch_files():
    """Verify generated integration patch files contain safe configuration and API helpers."""
    # Next.js patch
    next_patches = generate_integration_patch_files(
        framework=DetectedFramework.NEXT_JS,
        site_slug="test-site",
        public_api_url="https://api.cms.internal",
    )
    assert "cms.config.json" in next_patches
    assert "lib/cms.ts" in next_patches
    assert "test-site" in next_patches["cms.config.json"]
    assert "https://api.cms.internal" in next_patches["cms.config.json"]

    # Vite/React patch
    vite_patches = generate_integration_patch_files(
        framework=DetectedFramework.VITE_REACT,
        site_slug="test-site",
        public_api_url="https://api.cms.internal",
    )
    assert "cms.config.json" in vite_patches
    assert "src/cmsClient.ts" in vite_patches

    # Astro patch
    astro_patches = generate_integration_patch_files(
        framework=DetectedFramework.ASTRO,
        site_slug="test-site",
        public_api_url="https://api.cms.internal",
    )
    assert "cms.config.json" in astro_patches
    assert "src/lib/cms.js" in astro_patches


def test_open_integration_pr_success(github_setup, settings):
    """Admin can open an integration PR on a non-default branch."""
    settings.GITHUB_APP_ENABLED = True
    client = github_setup["client"]
    owner = github_setup["owner"]
    workspace = github_setup["workspace"]
    site = github_setup["site"]
    installation = github_setup["installation"]

    connection = SiteGitHubRepoConnection.objects.create(
        site=site,
        installation=installation,
        repo_full_name="acme-corp/nextjs-frontend",
        selected_branch="main",
        detected_framework=DetectedFramework.NEXT_JS,
        integration_status=IntegrationStatus.ANALYZED,
    )

    client.force_authenticate(user=owner)
    pr_url = reverse(
        "github_integration:site_github_open_pr",
        kwargs={"workspace_id": workspace.id, "site_id": site.id},
    )

    payload = {
        "pr_title": "Setup Headless CMS Integration",
        "commit_message": "Add CMS client and config",
    }
    resp = client.post(pr_url, payload, format="json")
    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.data["base_branch"] == "main"
    assert resp.data["new_branch"] == f"cms-integration-{site.slug}"
    assert "pull" in resp.data["pr_url"]
    assert "cms.config.json" in resp.data["committed_files"]

    connection.refresh_from_db()
    assert connection.integration_status == IntegrationStatus.PR_OPENED
    assert connection.last_pr_number == resp.data["pr_number"]
    assert connection.last_pr_url == resp.data["pr_url"]

    # Audit record
    audit = AuditEvent.objects.filter(action="GITHUB_PR_OPENED").first()
    assert audit is not None
    assert audit.payload["new_branch"] == f"cms-integration-{site.slug}"


def test_open_integration_pr_safety_invariant_rejects_base_branch(github_setup, settings):
    """PR creation must NEVER write directly to base branch (GH-4)."""
    settings.GITHUB_APP_ENABLED = True
    client = github_setup["client"]
    owner = github_setup["owner"]
    workspace = github_setup["workspace"]
    site = github_setup["site"]
    installation = github_setup["installation"]

    SiteGitHubRepoConnection.objects.create(
        site=site,
        installation=installation,
        repo_full_name="acme-corp/nextjs-frontend",
        selected_branch="main",
        detected_framework=DetectedFramework.NEXT_JS,
        integration_status=IntegrationStatus.ANALYZED,
    )

    client.force_authenticate(user=owner)
    pr_url = reverse(
        "github_integration:site_github_open_pr",
        kwargs={"workspace_id": workspace.id, "site_id": site.id},
    )

    # Attempting to commit directly to base branch
    payload = {
        "branch_name": "main",
    }
    resp = client.post(pr_url, payload, format="json")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "cannot be the same as the base branch" in str(resp.data).lower()
