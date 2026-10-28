"""Tests for recording visitor consent choices and decisions (CON-3)."""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.consent.models import (
    ConsentRecord,
    ConsentRecordStatus,
    PrivacyPolicyVersion,
    SiteConsentConfig,
)
from apps.sites.models import Site
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole

pytestmark = pytest.mark.django_db


@pytest.fixture
def consent_site():
    owner = User.objects.create_user(email="owner@records.com", password="Password123!")
    workspace = Workspace.objects.create(name="Rec WS", slug="rec-ws")
    WorkspaceMembership.objects.create(workspace=workspace, user=owner, role=WorkspaceRole.OWNER)
    site = Site.objects.create(
        workspace=workspace,
        name="Records Site",
        slug="records-site",
        allowed_origins=["https://site.com"],
    )
    config = SiteConsentConfig.objects.create(
        site=site,
        jurisdiction_mode="GDPR",
        gcm_enabled=True,
    )
    policy = PrivacyPolicyVersion.objects.create(
        site=site,
        version="2.0",
        title="Policy v2.0",
        is_active=True,
    )
    config.active_policy_version = policy
    config.save()
    return {"site": site, "config": config, "policy": policy}


def test_record_consent_full_opt_in(consent_site):
    client = APIClient()
    site = consent_site["site"]
    url = reverse("consent:public_consent_submit", kwargs={"site_slug": site.slug})

    payload = {
        "visitor_id": "visitor-abc-12345",
        "policy_version": "2.0",
        "categories": {
            "necessary": True,
            "analytics": True,
            "marketing": True,
            "preferences": True,
        },
    }

    resp = client.post(url, payload, format="json", HTTP_ORIGIN="https://site.com")
    assert resp.status_code == status.HTTP_201_CREATED

    data = resp.json()
    assert data["status"] == "RECORDED"
    assert data["decision_status"] == ConsentRecordStatus.GRANTED
    assert data["categories"]["analytics"] is True
    assert data["gcm_update"]["analytics_storage"] == "granted"
    assert data["gcm_update"]["ad_storage"] == "granted"

    # Verify database persistence
    record = ConsentRecord.objects.get(id=data["record_id"])
    assert record.visitor_id == "visitor-abc-12345"
    assert record.status == ConsentRecordStatus.GRANTED
    assert record.policy_version_string == "2.0"


def test_record_consent_partial_opt_in(consent_site):
    client = APIClient()
    site = consent_site["site"]
    url = reverse("consent:public_consent_submit", kwargs={"site_slug": site.slug})

    payload = {
        "visitor_id": "visitor-partial-9999",
        "categories": {
            "necessary": True,
            "analytics": True,
            "marketing": False,
            "preferences": False,
        },
    }

    resp = client.post(url, payload, format="json", HTTP_ORIGIN="https://site.com")
    assert resp.status_code == status.HTTP_201_CREATED

    data = resp.json()
    assert data["decision_status"] == ConsentRecordStatus.PARTIALLY_GRANTED
    assert data["gcm_update"]["analytics_storage"] == "granted"
    assert data["gcm_update"]["ad_storage"] == "denied"


def test_record_consent_full_rejection_of_optional(consent_site):
    client = APIClient()
    site = consent_site["site"]
    url = reverse("consent:public_consent_submit", kwargs={"site_slug": site.slug})

    payload = {
        "visitor_id": "visitor-deny-7777",
        "categories": {
            "necessary": True,
            "analytics": False,
            "marketing": False,
            "preferences": False,
        },
    }

    resp = client.post(url, payload, format="json", HTTP_ORIGIN="https://site.com")
    assert resp.status_code == status.HTTP_201_CREATED

    data = resp.json()
    assert data["decision_status"] == ConsentRecordStatus.DENIED
    assert data["gcm_update"]["analytics_storage"] == "denied"
    assert data["gcm_update"]["ad_storage"] == "denied"


def test_record_consent_rejection_of_false_necessary(consent_site):
    client = APIClient()
    site = consent_site["site"]
    url = reverse("consent:public_consent_submit", kwargs={"site_slug": site.slug})

    payload = {
        "visitor_id": "visitor-invalid-1",
        "categories": {
            "necessary": False,  # Illegal! Must be True
            "analytics": True,
        },
    }

    resp = client.post(url, payload, format="json", HTTP_ORIGIN="https://site.com")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


def test_record_consent_rejection_of_unknown_category(consent_site):
    client = APIClient()
    site = consent_site["site"]
    url = reverse("consent:public_consent_submit", kwargs={"site_slug": site.slug})

    payload = {
        "visitor_id": "visitor-invalid-2",
        "categories": {
            "necessary": True,
            "cryptominer": True,  # Unknown category!
        },
    }

    resp = client.post(url, payload, format="json", HTTP_ORIGIN="https://site.com")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


def test_record_consent_rejection_of_invalid_visitor_id(consent_site):
    client = APIClient()
    site = consent_site["site"]
    url = reverse("consent:public_consent_submit", kwargs={"site_slug": site.slug})

    # Too short (< 8 chars)
    payload = {
        "visitor_id": "abc",
        "categories": {"necessary": True},
    }
    resp = client.post(url, payload, format="json", HTTP_ORIGIN="https://site.com")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST

    # Malicious / illegal characters
    payload["visitor_id"] = "<script>alert(1)</script>"
    resp = client.post(url, payload, format="json", HTTP_ORIGIN="https://site.com")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
