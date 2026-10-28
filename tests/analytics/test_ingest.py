"""Tests for first-party event ingestion, schema enforcement, and abuse defense (ANA-4)."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.analytics.models import AnalyticsEvent, EventType, SiteAnalyticsConfig
from apps.sites.models import Domain, Site
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole


@pytest.fixture
def ingest_setup(db: None) -> dict[str, object]:
    user = User.objects.create_user(email="owner@ingest.org", password="SecurePassword123!")
    workspace = Workspace.objects.create(name="Ingest Org", slug="ingest-org")
    WorkspaceMembership.objects.create(workspace=workspace, user=user, role=WorkspaceRole.OWNER)

    site = Site.objects.create(
        workspace=workspace,
        name="Shop",
        slug="shop",
        allowed_origins=["https://shop.example.com"],
        is_active=True,
    )
    Domain.objects.create(site=site, hostname="shop.example.com", is_verified=True, is_primary=True)

    config = SiteAnalyticsConfig.objects.create(
        site=site,
        is_first_party_enabled=True,
        require_consent=False,  # disabled for baseline ingestion tests
    )

    return {
        "user": user,
        "workspace": workspace,
        "site": site,
        "config": config,
    }


@pytest.mark.django_db
def test_allowlisted_events_ingestion_success(ingest_setup: dict[str, object]) -> None:
    client = APIClient()
    site = ingest_setup["site"]
    assert isinstance(site, Site)

    url = reverse("analytics:public_ingest", kwargs={"site_slug": site.slug})

    # 1. Ingest page_view with allowlisted properties (path, referrer, title)
    pv_resp = client.post(
        url,
        {
            "event_type": "page_view",
            "visitor_id": "v-12345678-abcd",
            "session_id": "s-87654321-dcba",
            "path": "/products/laptop",
            "properties": {
                "referrer": "https://google.com/search",
                "title": "Ultra Laptop 2026",
            },
        },
        HTTP_ORIGIN="https://shop.example.com",
    )
    assert pv_resp.status_code == status.HTTP_202_ACCEPTED
    assert "event_id" in pv_resp.json()

    event = AnalyticsEvent.objects.get(id=pv_resp.json()["event_id"])
    assert event.event_type == EventType.PAGE_VIEW
    assert event.path == "/products/laptop"
    assert event.properties["title"] == "Ultra Laptop 2026"

    # 2. Ingest cta_click with allowlisted properties (cta_id, cta_text, target_url)
    cta_resp = client.post(
        url,
        {
            "event_type": "cta_click",
            "visitor_id": "v-12345678-abcd",
            "session_id": "s-87654321-dcba",
            "path": "/products/laptop",
            "properties": {
                "cta_id": "btn-buy-now",
                "cta_text": "Buy Now",
                "target_url": "/checkout",
            },
        },
        HTTP_ORIGIN="https://shop.example.com",
    )
    assert cta_resp.status_code == status.HTTP_202_ACCEPTED

    # 3. Ingest form_submit with allowlisted properties (form_id, form_name)
    form_resp = client.post(
        url,
        {
            "event_type": "form_submit",
            "visitor_id": "v-12345678-abcd",
            "session_id": "s-87654321-dcba",
            "path": "/contact",
            "properties": {
                "form_id": "form-support",
                "form_name": "Customer Support Inquiry",
            },
        },
        HTTP_ORIGIN="https://shop.example.com",
    )
    assert form_resp.status_code == status.HTTP_202_ACCEPTED


@pytest.mark.django_db
def test_rejection_of_arbitrary_events_and_properties(ingest_setup: dict[str, object]) -> None:
    client = APIClient()
    site = ingest_setup["site"]
    assert isinstance(site, Site)

    url = reverse("analytics:public_ingest", kwargs={"site_slug": site.slug})

    # 1. Non-allowlisted event type rejected
    bad_type = client.post(
        url,
        {
            "event_type": "user_password_entered",
            "visitor_id": "v-1",
            "session_id": "s-1",
            "path": "/login",
        },
        HTTP_ORIGIN="https://shop.example.com",
    )
    assert bad_type.status_code == status.HTTP_400_BAD_REQUEST

    # 2. Non-allowlisted properties rejected
    bad_props = client.post(
        url,
        {
            "event_type": "page_view",
            "visitor_id": "v-1",
            "session_id": "s-1",
            "path": "/home",
            "properties": {
                "random_injected_key": "arbitrary_value",
            },
        },
        HTTP_ORIGIN="https://shop.example.com",
    )
    assert bad_props.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_rejection_of_html_and_script_injection(ingest_setup: dict[str, object]) -> None:
    client = APIClient()
    site = ingest_setup["site"]
    assert isinstance(site, Site)

    url = reverse("analytics:public_ingest", kwargs={"site_slug": site.slug})

    xss_payload = client.post(
        url,
        {
            "event_type": "cta_click",
            "visitor_id": "v-1",
            "session_id": "s-1",
            "path": "/home",
            "properties": {
                "cta_id": "test-btn",
                "cta_text": "<script>alert(1)</script>",
            },
        },
        HTTP_ORIGIN="https://shop.example.com",
    )
    assert xss_payload.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_first_party_toggle_disabled(ingest_setup: dict[str, object]) -> None:
    client = APIClient()
    site = ingest_setup["site"]
    config = ingest_setup["config"]
    assert isinstance(site, Site)
    assert isinstance(config, SiteAnalyticsConfig)

    # Disable toggle
    config.is_first_party_enabled = False
    config.save()

    url = reverse("analytics:public_ingest", kwargs={"site_slug": site.slug})
    resp = client.post(
        url,
        {
            "event_type": "page_view",
            "visitor_id": "v-1",
            "session_id": "s-1",
            "path": "/home",
        },
        HTTP_ORIGIN="https://shop.example.com",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "disabled" in str(resp.json()["error"]).lower()
