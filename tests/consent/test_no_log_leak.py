"""Tests verifying that consent payloads and choices are never leaked into logs (CON-7)."""

import logging

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.common.logging import redact_sensitive
from apps.consent.models import PrivacyPolicyVersion, SiteConsentConfig
from apps.sites.models import Site
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole

pytestmark = pytest.mark.django_db


def test_redact_sensitive_handles_consent_and_categories_payload():
    raw_payload = {
        "visitor_id": "visitor-test-12345",
        "consent_payload": {"necessary": True, "marketing": False},
        "categories_payload": {"analytics": True},
        "safe_field": "consent_update_completed",
    }
    redacted = redact_sensitive(raw_payload)
    assert redacted["consent_payload"] == "[REDACTED]"
    assert redacted["categories_payload"] == "[REDACTED]"
    assert redacted["safe_field"] == "consent_update_completed"


def test_public_consent_submission_no_log_leak(caplog):
    owner = User.objects.create_user(email="owner@nolog.com", password="Password123!")
    workspace = Workspace.objects.create(name="NoLog WS", slug="nolog-ws")
    WorkspaceMembership.objects.create(workspace=workspace, user=owner, role=WorkspaceRole.OWNER)
    site = Site.objects.create(
        workspace=workspace,
        name="NoLog Site",
        slug="nolog-site",
        allowed_origins=["https://site.com"],
    )
    config = SiteConsentConfig.objects.create(site=site)
    policy = PrivacyPolicyVersion.objects.create(
        site=site, version="1.0", title="v1", is_active=True
    )
    config.active_policy_version = policy
    config.save()

    client = APIClient()
    url = reverse("consent:public_consent_submit", kwargs={"site_slug": site.slug})

    secret_marker = "sensitive-secret-token-marker-987654321"
    payload = {
        "visitor_id": "visitor-audit-test",
        "categories": {"necessary": True, "analytics": True},
        # Pass a mock or query param
    }

    with caplog.at_level(logging.INFO):
        resp = client.post(
            f"{url}?secret_token={secret_marker}",
            payload,
            format="json",
            HTTP_ORIGIN="https://site.com",
        )
        assert resp.status_code == status.HTTP_201_CREATED

    # Verify that secret_marker does not appear anywhere in standard access log
    for record in caplog.records:
        assert secret_marker not in record.message
        assert secret_marker not in str(record.__dict__)
