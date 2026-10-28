"""Tests for privacy preservation, IP exclusion, UA coarsening, and PII sanitization (ANA-5)."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.analytics.models import AnalyticsEvent, DeviceCategory, SiteAnalyticsConfig
from apps.analytics.validators import coarsen_user_agent, sanitize_url_query
from apps.sites.models import Site
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole


def test_zero_raw_ip_storage_guarantee() -> None:
    """Verify that AnalyticsEvent model schema completely excludes IP address fields (ANA-5)."""
    field_names = [f.name for f in AnalyticsEvent._meta.get_fields()]
    assert "ip" not in field_names
    assert "ip_address" not in field_names
    assert "client_ip" not in field_names
    assert "remote_addr" not in field_names


def test_coarsen_user_agent_logic() -> None:
    # Desktop Chrome
    chrome_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"  # noqa: E501
    dev, browser = coarsen_user_agent(chrome_ua)
    assert dev == "DESKTOP"
    assert browser == "CHROME"

    # Mobile iPhone Safari
    iphone_ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"  # noqa: E501
    dev, browser = coarsen_user_agent(iphone_ua)
    assert dev == "MOBILE"
    assert browser == "SAFARI"

    # Tablet iPad
    ipad_ua = (
        "Mozilla/5.0 (iPad; CPU OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko)"
    )
    dev, browser = coarsen_user_agent(ipad_ua)
    assert dev == "TABLET"

    # Search crawler / Bot
    bot_ua = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    dev, browser = coarsen_user_agent(bot_ua)
    assert dev == "BOT"


def test_sanitize_url_query_pii_stripping() -> None:
    url_with_pii = "/checkout?email=alice%40corp.com&token=secret123&utm_source=google"
    cleaned = sanitize_url_query(url_with_pii)
    assert "email=" not in cleaned
    assert "token=" not in cleaned
    assert "utm_source=google" in cleaned


@pytest.mark.django_db
def test_pii_in_properties_rejected(db: None) -> None:
    user = User.objects.create_user(email="owner@privacy.org", password="SecurePassword123!")
    workspace = Workspace.objects.create(name="Privacy Org", slug="privacy-org")
    WorkspaceMembership.objects.create(workspace=workspace, user=user, role=WorkspaceRole.OWNER)

    site = Site.objects.create(workspace=workspace, name="Health Portal", slug="health-portal")
    SiteAnalyticsConfig.objects.create(
        site=site, is_first_party_enabled=True, require_consent=False
    )

    client = APIClient()
    url = reverse("analytics:public_ingest", kwargs={"site_slug": site.slug})

    # 1. Email in property rejected
    email_resp = client.post(
        url,
        {
            "event_type": "cta_click",
            "visitor_id": "v-1",
            "session_id": "s-1",
            "path": "/home",
            "properties": {
                "cta_id": "btn-newsletter",
                "cta_text": "Sign up with john.doe@example.com",
            },
        },
    )
    assert email_resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "pii" in str(email_resp.json()["error"]).lower()

    # 2. SSN pattern in property rejected
    ssn_resp = client.post(
        url,
        {
            "event_type": "form_submit",
            "visitor_id": "v-1",
            "session_id": "s-1",
            "path": "/apply",
            "properties": {
                "form_id": "application",
                "form_name": "Applicant 123-45-6789",
            },
        },
    )
    assert ssn_resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_user_agent_stored_as_coarse_category_only(db: None) -> None:
    user = User.objects.create_user(email="owner@coarse.org", password="SecurePassword123!")
    workspace = Workspace.objects.create(name="Coarse Org", slug="coarse-org")
    WorkspaceMembership.objects.create(workspace=workspace, user=user, role=WorkspaceRole.OWNER)

    site = Site.objects.create(workspace=workspace, name="Tech Site", slug="tech-site")
    SiteAnalyticsConfig.objects.create(
        site=site, is_first_party_enabled=True, require_consent=False
    )

    client = APIClient()
    url = reverse("analytics:public_ingest", kwargs={"site_slug": site.slug})

    resp = client.post(
        url,
        {
            "event_type": "page_view",
            "visitor_id": "v-1",
            "session_id": "s-1",
            "path": "/articles/python-tips",
            "properties": {"title": "Python Tips"},
        },
        HTTP_USER_AGENT="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",  # noqa: E501
    )
    assert resp.status_code == status.HTTP_202_ACCEPTED

    event = AnalyticsEvent.objects.get(id=resp.json()["event_id"])
    assert event.device_category == DeviceCategory.MOBILE
    assert event.browser_family == "SAFARI"
