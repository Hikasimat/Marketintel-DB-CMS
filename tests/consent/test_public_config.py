"""Tests for public consent configuration endpoint and browser contracts (CON-2)."""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.consent.models import PrivacyPolicyVersion, SiteConsentConfig
from apps.sites.models import Site
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole

pytestmark = pytest.mark.django_db


@pytest.fixture
def site_with_config():
    owner = User.objects.create_user(email="owner@public-consent.com", password="Password123!")
    workspace = Workspace.objects.create(name="Pub WS", slug="pub-ws")
    WorkspaceMembership.objects.create(workspace=workspace, user=owner, role=WorkspaceRole.OWNER)
    site = Site.objects.create(
        workspace=workspace,
        name="Public Site",
        slug="public-site",
        allowed_origins=["https://example.com"],
    )
    config = SiteConsentConfig.objects.create(
        site=site,
        jurisdiction_mode="GDPR",
        gcm_enabled=True,
        gcm_default_analytics_storage="denied",
        gcm_default_ad_storage="denied",
    )
    version = PrivacyPolicyVersion.objects.create(
        site=site,
        version="1.0",
        title="Privacy Policy v1.0",
        body="This is our policy body.",
        is_active=True,
    )
    config.active_policy_version = version
    config.save()
    return {"site": site, "config": config, "version": version}


def test_public_consent_config_success(site_with_config):
    client = APIClient()
    site = site_with_config["site"]
    url = reverse("consent:public_banner_config", kwargs={"site_slug": site.slug})

    # Request with allowed origin
    resp = client.get(url, HTTP_ORIGIN="https://example.com")
    assert resp.status_code == status.HTTP_200_OK

    data = resp.json()
    assert data["is_enabled"] is True
    assert data["jurisdiction_mode"] == "GDPR"
    assert "categories" in data
    assert "necessary" in data["categories"]
    assert data["categories"]["necessary"]["required"] is True

    # Active policy metadata
    assert data["active_policy"] is not None
    assert data["active_policy"]["version"] == "1.0"
    assert data["active_policy"]["title"] == "Privacy Policy v1.0"

    # GCM defaults
    assert data["gcm_enabled"] is True
    assert data["gcm_defaults"]["analytics_storage"] == "denied"
    assert data["gcm_defaults"]["ad_storage"] == "denied"


def test_public_consent_config_origin_rejection(site_with_config):
    client = APIClient()
    site = site_with_config["site"]
    url = reverse("consent:public_banner_config", kwargs={"site_slug": site.slug})

    # Unauthorized origin
    resp = client.get(url, HTTP_ORIGIN="https://malicious.com")
    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_public_consent_config_gcm_disabled(site_with_config):
    client = APIClient()
    site = site_with_config["site"]
    config = site_with_config["config"]
    config.gcm_enabled = False
    config.save()

    url = reverse("consent:public_banner_config", kwargs={"site_slug": site.slug})
    resp = client.get(url, HTTP_ORIGIN="https://example.com")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["gcm_enabled"] is False
    assert resp.json()["gcm_defaults"] == {}
