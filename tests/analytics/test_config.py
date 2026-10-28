"""Tests for site analytics configuration, ID format validation, and public config (ANA-1)."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.analytics.models import SiteAnalyticsConfig
from apps.analytics.validators import validate_gtm_container_id, validate_measurement_id
from apps.sites.models import Domain, Site
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole


@pytest.fixture
def analytics_setup(db: None) -> dict[str, object]:
    admin = User.objects.create_user(email="admin@analytics.org", password="SecurePassword123!")
    analyst = User.objects.create_user(email="analyst@analytics.org", password="SecurePassword123!")

    workspace = Workspace.objects.create(name="Analytics Org", slug="analytics-org")
    WorkspaceMembership.objects.create(workspace=workspace, user=admin, role=WorkspaceRole.ADMIN)
    WorkspaceMembership.objects.create(
        workspace=workspace, user=analyst, role=WorkspaceRole.ANALYST
    )

    site = Site.objects.create(
        workspace=workspace,
        name="Portal",
        slug="portal",
        allowed_origins=["https://portal.example.com"],
        is_active=True,
    )
    Domain.objects.create(
        site=site, hostname="portal.example.com", is_verified=True, is_primary=True
    )

    return {
        "admin": admin,
        "analyst": analyst,
        "workspace": workspace,
        "site": site,
    }


def test_measurement_id_validator() -> None:
    # Valid GA4 IDs
    assert validate_measurement_id("G-12345ABCDE") == "G-12345ABCDE"
    assert validate_measurement_id("g-999xyz") == "G-999XYZ"
    assert validate_measurement_id("") == ""

    # Invalid formats
    with pytest.raises(ValidationError, match="Invalid GA4 Measurement ID"):
        validate_measurement_id("UA-123456-1")  # Universal Analytics not supported

    with pytest.raises(ValidationError, match="Invalid GA4 Measurement ID"):
        validate_measurement_id("invalid-format")


def test_gtm_container_id_validator() -> None:
    # Valid GTM IDs
    assert validate_gtm_container_id("GTM-ABC1234") == "GTM-ABC1234"
    assert validate_gtm_container_id("gtm-xyz") == "GTM-XYZ"
    assert validate_gtm_container_id("") == ""

    # Invalid formats
    with pytest.raises(ValidationError, match="Invalid GTM Container ID"):
        validate_gtm_container_id("TAG-12345")


@pytest.mark.django_db
def test_analytics_config_api_crud_and_permissions(analytics_setup: dict[str, object]) -> None:
    client = APIClient()
    admin = analytics_setup["admin"]
    analyst = analytics_setup["analyst"]
    workspace = analytics_setup["workspace"]
    site = analytics_setup["site"]
    assert isinstance(workspace, Workspace)
    assert isinstance(site, Site)

    url = reverse(
        "analytics:config",
        kwargs={"workspace_id": workspace.id, "site_id": site.id},
    )

    # 1. Analyst can read config
    client.force_authenticate(user=analyst)
    resp = client.get(url)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["is_first_party_enabled"] is False

    # 2. Analyst cannot update config (requires admin)
    patch_resp = client.patch(url, {"measurement_id": "G-NEW12345"})
    assert patch_resp.status_code == status.HTTP_403_FORBIDDEN

    # 3. Admin updates config
    client.force_authenticate(user=admin)
    update_resp = client.patch(
        url,
        {
            "measurement_id": "G-ABC999",
            "gtm_container_id": "GTM-XYZ888",
            "is_first_party_enabled": True,
            "retention_days": 180,
            "require_consent": True,
        },
    )
    assert update_resp.status_code == status.HTTP_200_OK
    data = update_resp.json()
    assert data["measurement_id"] == "G-ABC999"
    assert data["gtm_container_id"] == "GTM-XYZ888"
    assert data["is_first_party_enabled"] is True
    assert data["retention_days"] == 180

    # 4. Invalid retention period rejected
    bad_resp = client.patch(url, {"retention_days": 3})  # min is 7
    assert bad_resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_public_analytics_config_endpoint(analytics_setup: dict[str, object]) -> None:
    client = APIClient()
    site = analytics_setup["site"]
    assert isinstance(site, Site)

    SiteAnalyticsConfig.objects.create(
        site=site,
        measurement_id="G-PUBLIC123",
        gtm_container_id="GTM-PUB456",
        is_first_party_enabled=True,
    )

    url = reverse("analytics:public_config", kwargs={"site_slug": site.slug})

    # Authorized browser origin
    resp = client.get(url, HTTP_ORIGIN="https://portal.example.com")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["measurement_id"] == "G-PUBLIC123"
    assert data["gtm_container_id"] == "GTM-PUB456"
    assert data["is_first_party_enabled"] is True
    # Ensure no internal DB fields are leaked
    assert "id" not in data
    assert "retention_days" not in data

    # Unauthorized origin rejected (CT-6)
    bad_origin_resp = client.get(url, HTTP_ORIGIN="https://malicious-site.com")
    assert bad_origin_resp.status_code == status.HTTP_403_FORBIDDEN
