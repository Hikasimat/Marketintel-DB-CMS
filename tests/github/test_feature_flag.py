"""Tests for GitHub App feature flag enforcement (GH-7)."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status

pytestmark = pytest.mark.django_db


def test_feature_flag_disabled_rejects_endpoints(github_setup, settings):
    """When GITHUB_APP_ENABLED=False, all GitHub integration endpoints return HTTP 403."""
    settings.GITHUB_APP_ENABLED = False
    client = github_setup["client"]
    owner = github_setup["owner"]
    workspace = github_setup["workspace"]
    site = github_setup["site"]

    client.force_authenticate(user=owner)

    # 1. Installations list
    list_url = reverse(
        "github_integration:workspace_github_installation_list",
        kwargs={"workspace_id": workspace.id},
    )
    resp = client.get(list_url)
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert "disabled" in str(resp.data).lower()

    # 2. Site connect
    connect_url = reverse(
        "github_integration:site_github_connect",
        kwargs={"workspace_id": workspace.id, "site_id": site.id},
    )
    resp = client.post(
        connect_url,
        {"installation_id": 12345, "repo_full_name": "acme-corp/nextjs-frontend"},
        format="json",
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    # 3. Webhook endpoint
    webhook_url = reverse("github_integration:github_webhook")
    client.force_authenticate(user=None)
    resp = client.post(webhook_url, {}, format="json")
    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_feature_flag_enabled_allows_endpoints(github_setup, settings):
    """When GITHUB_APP_ENABLED=True, authenticated workspace members access endpoints."""
    settings.GITHUB_APP_ENABLED = True
    client = github_setup["client"]
    owner = github_setup["owner"]
    workspace = github_setup["workspace"]

    client.force_authenticate(user=owner)
    list_url = reverse(
        "github_integration:workspace_github_installation_list",
        kwargs={"workspace_id": workspace.id},
    )
    resp = client.get(list_url)
    assert resp.status_code == status.HTTP_200_OK
    assert len(resp.data) == 1
    assert resp.data[0]["installation_id"] == 12345
