"""Tests for GitHub webhook verification, replay defense, and lifecycle handling (GH-6)."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from django.urls import reverse
from rest_framework import status

from apps.common.logging import redact_sensitive
from apps.github_integration.models import (
    GitHubWebhookDelivery,
    IntegrationStatus,
    SiteGitHubRepoConnection,
)

pytestmark = pytest.mark.django_db


def _generate_signature(secret: str, payload_bytes: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_webhook_hmac_signature_validation(github_setup, settings):
    """Test HMAC-SHA256 signature verification over raw body (GH-6)."""
    settings.GITHUB_APP_ENABLED = True
    settings.GITHUB_APP_WEBHOOK_SECRET = "test-webhook-secret-key-12345"

    client = github_setup["client"]
    url = reverse("github_integration:github_webhook")

    payload = {"action": "created", "installation": {"id": 12345}}
    body_bytes = json.dumps(payload).encode("utf-8")

    # 1. Missing signature header -> 401
    resp = client.post(
        url,
        data=body_bytes,
        content_type="application/json",
        HTTP_X_GITHUB_DELIVERY="deliv-001",
        HTTP_X_GITHUB_EVENT="installation",
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
    assert "missing x-hub-signature" in str(resp.data).lower()

    # 2. Invalid signature -> 401
    resp = client.post(
        url,
        data=body_bytes,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256="sha256=invalidhexsignature000000000000000000000000000000000000000000000",
        HTTP_X_GITHUB_DELIVERY="deliv-002",
        HTTP_X_GITHUB_EVENT="installation",
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
    assert "invalid webhook signature" in str(resp.data).lower()

    # 3. Valid signature -> 200
    valid_sig = _generate_signature(settings.GITHUB_APP_WEBHOOK_SECRET, body_bytes)
    resp = client.post(
        url,
        data=body_bytes,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=valid_sig,
        HTTP_X_GITHUB_DELIVERY="deliv-003",
        HTTP_X_GITHUB_EVENT="installation",
    )
    assert resp.status_code == status.HTTP_200_OK


def test_webhook_delivery_replay_protection(github_setup, settings):
    """Replayed delivery IDs are ignored to prevent duplicate processing (GH-6)."""
    settings.GITHUB_APP_ENABLED = True
    settings.GITHUB_APP_WEBHOOK_SECRET = "test-webhook-secret-key-12345"

    client = github_setup["client"]
    url = reverse("github_integration:github_webhook")

    payload = {"action": "created", "installation": {"id": 12345}}
    body_bytes = json.dumps(payload).encode("utf-8")
    sig = _generate_signature(settings.GITHUB_APP_WEBHOOK_SECRET, body_bytes)

    # First delivery -> processed
    resp1 = client.post(
        url,
        data=body_bytes,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=sig,
        HTTP_X_GITHUB_DELIVERY="deliv-replay-100",
        HTTP_X_GITHUB_EVENT="installation",
    )
    assert resp1.status_code == status.HTTP_200_OK
    assert GitHubWebhookDelivery.objects.filter(delivery_id="deliv-replay-100").exists()

    # Replay of same delivery ID -> ignored
    resp2 = client.post(
        url,
        data=body_bytes,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=sig,
        HTTP_X_GITHUB_DELIVERY="deliv-replay-100",
        HTTP_X_GITHUB_EVENT="installation",
    )
    assert resp2.status_code == status.HTTP_200_OK
    assert resp2.data["status"] == "ignored"


def test_webhook_installation_deleted_lifecycle(github_setup, settings):
    """installation.deleted webhook deactivates installation and disconnects sites."""
    settings.GITHUB_APP_ENABLED = True
    settings.GITHUB_APP_WEBHOOK_SECRET = "test-webhook-secret-key-12345"

    client = github_setup["client"]
    url = reverse("github_integration:github_webhook")
    site = github_setup["site"]
    installation = github_setup["installation"]

    connection = SiteGitHubRepoConnection.objects.create(
        site=site,
        installation=installation,
        repo_full_name="acme-corp/nextjs-frontend",
        integration_status=IntegrationStatus.CONNECTED,
    )

    payload = {
        "action": "deleted",
        "installation": {"id": installation.installation_id},
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    sig = _generate_signature(settings.GITHUB_APP_WEBHOOK_SECRET, body_bytes)

    resp = client.post(
        url,
        data=body_bytes,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=sig,
        HTTP_X_GITHUB_DELIVERY="deliv-deleted-001",
        HTTP_X_GITHUB_EVENT="installation",
    )
    assert resp.status_code == status.HTTP_200_OK

    installation.refresh_from_db()
    assert installation.is_active is False

    connection.refresh_from_db()
    assert connection.integration_status == IntegrationStatus.DISCONNECTED
    assert "uninstalled by customer" in connection.last_error


def test_webhook_installation_suspend_and_unsuspend(github_setup, settings):
    """installation.suspend and unsuspend webhooks toggle active state."""
    settings.GITHUB_APP_ENABLED = True
    settings.GITHUB_APP_WEBHOOK_SECRET = "test-webhook-secret-key-12345"

    client = github_setup["client"]
    url = reverse("github_integration:github_webhook")
    installation = github_setup["installation"]

    # 1. Suspend
    payload_suspend = {
        "action": "suspend",
        "installation": {"id": installation.installation_id},
    }
    body_suspend = json.dumps(payload_suspend).encode("utf-8")
    sig_suspend = _generate_signature(settings.GITHUB_APP_WEBHOOK_SECRET, body_suspend)

    resp = client.post(
        url,
        data=body_suspend,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=sig_suspend,
        HTTP_X_GITHUB_DELIVERY="deliv-suspend-001",
        HTTP_X_GITHUB_EVENT="installation",
    )
    assert resp.status_code == status.HTTP_200_OK

    installation.refresh_from_db()
    assert installation.is_active is False
    assert installation.suspended_at is not None

    # 2. Unsuspend
    payload_unsuspend = {
        "action": "unsuspend",
        "installation": {"id": installation.installation_id},
    }
    body_unsuspend = json.dumps(payload_unsuspend).encode("utf-8")
    sig_unsuspend = _generate_signature(settings.GITHUB_APP_WEBHOOK_SECRET, body_unsuspend)

    resp = client.post(
        url,
        data=body_unsuspend,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=sig_unsuspend,
        HTTP_X_GITHUB_DELIVERY="deliv-unsuspend-001",
        HTTP_X_GITHUB_EVENT="installation",
    )
    assert resp.status_code == status.HTTP_200_OK

    installation.refresh_from_db()
    assert installation.is_active is True
    assert installation.suspended_at is None


def test_webhook_repositories_removed(github_setup, settings):
    """installation_repositories.removed revokes repository connection."""
    settings.GITHUB_APP_ENABLED = True
    settings.GITHUB_APP_WEBHOOK_SECRET = "test-webhook-secret-key-12345"

    client = github_setup["client"]
    url = reverse("github_integration:github_webhook")
    site = github_setup["site"]
    installation = github_setup["installation"]

    connection = SiteGitHubRepoConnection.objects.create(
        site=site,
        installation=installation,
        repo_full_name="acme-corp/nextjs-frontend",
        integration_status=IntegrationStatus.CONNECTED,
    )

    payload = {
        "action": "removed",
        "installation": {"id": installation.installation_id},
        "repositories_removed": [{"full_name": "acme-corp/nextjs-frontend"}],
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    sig = _generate_signature(settings.GITHUB_APP_WEBHOOK_SECRET, body_bytes)

    resp = client.post(
        url,
        data=body_bytes,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=sig,
        HTTP_X_GITHUB_DELIVERY="deliv-repos-removed-001",
        HTTP_X_GITHUB_EVENT="installation_repositories",
    )
    assert resp.status_code == status.HTTP_200_OK

    connection.refresh_from_db()
    assert connection.integration_status == IntegrationStatus.DISCONNECTED
    assert "revoked in github app settings" in connection.last_error.lower()


def test_sensitive_github_keys_redaction():
    """Verify private keys and webhook secrets are redacted in log scrubbing."""
    test_data = {
        "account": "test-org",
        "github_private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0...",
        "webhook_secret": "super-secret-hex-value-12345",
    }
    redacted = redact_sensitive(test_data)
    assert redacted["github_private_key"] == "[REDACTED]"
    assert redacted["webhook_secret"] == "[REDACTED]"
    assert redacted["account"] == "test-org"
