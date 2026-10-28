"""Tests for GitHub App installation registration and lifecycle (GH-1)."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status

from apps.audit.models import AuditEvent
from apps.github_integration.models import (
    IntegrationStatus,
    SiteGitHubRepoConnection,
)

pytestmark = pytest.mark.django_db


def test_installation_rbac_and_isolation(github_setup, settings):
    """Test RBAC role enforcement and tenant isolation on installation endpoints."""
    settings.GITHUB_APP_ENABLED = True
    client = github_setup["client"]
    owner = github_setup["owner"]
    editor = github_setup["editor"]
    non_member = github_setup["non_member"]
    workspace = github_setup["workspace"]

    list_url = reverse(
        "github_integration:workspace_github_installation_list",
        kwargs={"workspace_id": workspace.id},
    )

    # 1. Unauthenticated -> 401
    resp = client.get(list_url)
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    # 2. Non-member -> 404
    client.force_authenticate(user=non_member)
    resp = client.get(list_url)
    assert resp.status_code == status.HTTP_404_NOT_FOUND

    # 3. Editor can GET
    client.force_authenticate(user=editor)
    resp = client.get(list_url)
    assert resp.status_code == status.HTTP_200_OK
    assert len(resp.data) == 1

    # 4. Editor cannot register installation (POST) -> 403
    payload = {
        "installation_id": 99999,
        "account_login": "editor-org",
        "account_type": "Organization",
    }
    resp = client.post(list_url, payload, format="json")
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    # 5. Owner can register installation (POST) -> 201
    client.force_authenticate(user=owner)
    resp = client.post(list_url, payload, format="json")
    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.data["installation_id"] == 99999
    assert resp.data["account_login"] == "editor-org"

    # Audit event recorded
    audit = AuditEvent.objects.filter(action="GITHUB_APP_INSTALLED").first()
    assert audit is not None
    assert audit.payload["installation_id"] == 99999


def test_installation_delete_lifecycle(github_setup, settings):
    """Deleting an installation marks it inactive and disconnects attached sites."""
    settings.GITHUB_APP_ENABLED = True
    client = github_setup["client"]
    owner = github_setup["owner"]
    workspace = github_setup["workspace"]
    site = github_setup["site"]
    installation = github_setup["installation"]

    # Attach site
    connection = SiteGitHubRepoConnection.objects.create(
        site=site,
        installation=installation,
        repo_full_name="acme-corp/nextjs-frontend",
        integration_status=IntegrationStatus.CONNECTED,
    )

    detail_url = reverse(
        "github_integration:workspace_github_installation_detail",
        kwargs={"workspace_id": workspace.id, "installation_id": installation.installation_id},
    )

    client.force_authenticate(user=owner)
    resp = client.delete(detail_url)
    assert resp.status_code == status.HTTP_204_NO_CONTENT

    installation.refresh_from_db()
    assert installation.is_active is False

    connection.refresh_from_db()
    assert connection.integration_status == IntegrationStatus.DISCONNECTED
    assert "removed by workspace administrator" in connection.last_error

    audit = AuditEvent.objects.filter(action="GITHUB_APP_UNINSTALLED").first()
    assert audit is not None
    assert audit.payload["installation_id"] == installation.installation_id
