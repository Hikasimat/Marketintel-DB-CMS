"""Tests for consent gating and contract enforcement on event ingestion (ANA-6)."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.analytics.models import AnalyticsEvent, SiteAnalyticsConfig
from apps.sites.models import Site
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole


@pytest.fixture
def consent_setup(db: None) -> dict[str, object]:
    user = User.objects.create_user(email="owner@consent.org", password="SecurePassword123!")
    workspace = Workspace.objects.create(name="Consent Org", slug="consent-org")
    WorkspaceMembership.objects.create(workspace=workspace, user=user, role=WorkspaceRole.OWNER)

    site = Site.objects.create(workspace=workspace, name="GDPR Site", slug="gdpr-site")
    config = SiteAnalyticsConfig.objects.create(
        site=site,
        is_first_party_enabled=True,
        require_consent=True,  # Consent required
    )

    return {
        "user": user,
        "workspace": workspace,
        "site": site,
        "config": config,
    }


@pytest.mark.django_db
def test_consent_required_rejects_without_consent(consent_setup: dict[str, object]) -> None:
    client = APIClient()
    site = consent_setup["site"]
    assert isinstance(site, Site)

    url = reverse("analytics:public_ingest", kwargs={"site_slug": site.slug})

    # 1. Submission without consent_granted flag fails
    resp = client.post(
        url,
        {
            "event_type": "page_view",
            "visitor_id": "v-no-consent",
            "session_id": "s-1",
            "path": "/pricing",
            "consent_granted": False,
        },
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert "consent" in resp.json()["error"]["message"].lower()

    # 2. Submission with consent_granted=True succeeds
    success_resp = client.post(
        url,
        {
            "event_type": "page_view",
            "visitor_id": "v-with-consent",
            "session_id": "s-1",
            "path": "/pricing",
            "consent_granted": True,
        },
    )
    assert success_resp.status_code == status.HTTP_202_ACCEPTED
    event = AnalyticsEvent.objects.get(id=success_resp.json()["event_id"])
    assert event.consent_basis == "EXPLICIT_CONSENT"


@pytest.mark.django_db
def test_consent_not_required_records_legitimate_interest(
    consent_setup: dict[str, object],
) -> None:
    client = APIClient()
    site = consent_setup["site"]
    config = consent_setup["config"]
    assert isinstance(site, Site)
    assert isinstance(config, SiteAnalyticsConfig)

    # Disable consent requirement on site config
    config.require_consent = False
    config.save()

    url = reverse("analytics:public_ingest", kwargs={"site_slug": site.slug})

    resp = client.post(
        url,
        {
            "event_type": "page_view",
            "visitor_id": "v-legit",
            "session_id": "s-1",
            "path": "/about",
            "consent_granted": False,
        },
    )
    assert resp.status_code == status.HTTP_202_ACCEPTED
    event = AnalyticsEvent.objects.get(id=resp.json()["event_id"])
    assert event.consent_basis == "LEGITIMATE_INTEREST"
