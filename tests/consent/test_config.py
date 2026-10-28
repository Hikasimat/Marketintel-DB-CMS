"""Tests for per-site consent configuration (CON-1)."""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.consent.models import JurisdictionMode, SiteConsentConfig
from apps.sites.models import Site
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole

pytestmark = pytest.mark.django_db


@pytest.fixture
def site_setup():
    owner = User.objects.create_user(email="owner@consent-test.com", password="Password123!")
    analyst = User.objects.create_user(email="analyst@consent-test.com", password="Password123!")
    workspace = Workspace.objects.create(name="Consent WS", slug="consent-ws")
    WorkspaceMembership.objects.create(workspace=workspace, user=owner, role=WorkspaceRole.OWNER)
    WorkspaceMembership.objects.create(
        workspace=workspace, user=analyst, role=WorkspaceRole.ANALYST
    )
    site = Site.objects.create(workspace=workspace, name="Consent Site", slug="consent-site")
    return {"owner": owner, "analyst": analyst, "workspace": workspace, "site": site}


def test_default_consent_config_creation_and_categories(site_setup):
    site = site_setup["site"]
    config = SiteConsentConfig.objects.create(site=site)

    assert config.is_enabled is True
    assert config.jurisdiction_mode == JurisdictionMode.GDPR
    assert config.retention_days == 365

    all_cats = config.get_all_categories()
    assert "necessary" in all_cats
    assert all_cats["necessary"]["required"] is True
    assert all_cats["necessary"]["default_state"] is True

    for optional_cat in ("analytics", "marketing", "preferences"):
        assert optional_cat in all_cats
        assert all_cats[optional_cat]["required"] is False
        assert all_cats[optional_cat]["default_state"] is False


def test_site_consent_config_api_permissions(site_setup):
    client = APIClient()
    workspace = site_setup["workspace"]
    site = site_setup["site"]
    url = reverse(
        "consent:site_consent_config",
        kwargs={"workspace_id": workspace.id, "site_id": site.id},
    )

    # 1. Unauthenticated -> 401
    resp = client.get(url)
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    # 2. Analyst (member) -> GET 200, PATCH 403
    client.force_authenticate(user=site_setup["analyst"])
    resp = client.get(url)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["is_enabled"] is True

    patch_resp = client.patch(url, {"jurisdiction_mode": "CCPA_CPRA"}, format="json")
    assert patch_resp.status_code == status.HTTP_403_FORBIDDEN

    # 3. Owner (admin) -> PATCH 200
    client.force_authenticate(user=site_setup["owner"])
    patch_resp = client.patch(
        url,
        {
            "jurisdiction_mode": "CCPA_CPRA",
            "retention_days": 180,
            "gcm_enabled": True,
            "gcm_default_analytics_storage": "denied",
        },
        format="json",
    )
    assert patch_resp.status_code == status.HTTP_200_OK
    data = patch_resp.json()
    assert data["jurisdiction_mode"] == "CCPA_CPRA"
    assert data["retention_days"] == 180
    assert data["gcm_enabled"] is True


def test_retention_days_validation(site_setup):
    client = APIClient()
    client.force_authenticate(user=site_setup["owner"])
    workspace = site_setup["workspace"]
    site = site_setup["site"]
    url = reverse(
        "consent:site_consent_config",
        kwargs={"workspace_id": workspace.id, "site_id": site.id},
    )

    # Below minimum (30)
    resp = client.patch(url, {"retention_days": 10}, format="json")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST

    # Above maximum (1095)
    resp = client.patch(url, {"retention_days": 2000}, format="json")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


def test_consent_models_clean_and_str(site_setup):
    from django.core.exceptions import ValidationError as DjangoValidationError

    from apps.consent.models import ConsentRecord, PrivacyPolicyVersion

    site = site_setup["site"]
    config = SiteConsentConfig(site=site, retention_days=20)
    with pytest.raises(DjangoValidationError):
        config.clean()

    # Non-dict categories
    config.retention_days = 365
    config.categories = ["invalid_list"]
    with pytest.raises(DjangoValidationError):
        config.clean()

    # Non-dict category value
    config.categories = {"custom": "not_a_dict"}
    with pytest.raises(DjangoValidationError):
        config.clean()

    # Redefine necessary
    config.categories = {"necessary": {"title": "Attempted override"}}
    with pytest.raises(DjangoValidationError):
        config.clean()

    # String representations
    config.categories = {}
    config.save()
    assert str(config) == f"Consent Config for {site.name}"

    policy = PrivacyPolicyVersion.objects.create(
        site=site, version="3.0", title="v3", is_active=True
    )
    assert str(policy) == f"{site.name} Policy v3.0"

    from django.utils import timezone

    record = ConsentRecord.objects.create(
        site=site,
        visitor_id="visitor-str-check-12345",
        policy_version=policy,
        policy_version_string="3.0",
        categories={"necessary": True},
        expires_at=timezone.now(),
    )
    assert "visitor-" in str(record)
