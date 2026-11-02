"""Tests for GA4 gtag snippet generator, OAuth authorization, properties, and reports."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.analytics.models import GA4Connection, SiteAnalyticsConfig
from apps.sites.models import Site
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole

pytestmark = pytest.mark.django_db


@dataclass
class GA4Setup:
    user: User
    workspace: Workspace
    site: Site
    config: SiteAnalyticsConfig


@pytest.fixture
def ga4_setup() -> GA4Setup:
    user = User.objects.create_user(email="owner@ga4test.com", password="SecurePassword123!")
    workspace = Workspace.objects.create(name="GA4 Workspace", slug="ga4-workspace")
    WorkspaceMembership.objects.create(workspace=workspace, user=user, role=WorkspaceRole.OWNER)
    site = Site.objects.create(
        workspace=workspace, name="GA4 Site", slug="ga4-site", default_locale="en-US"
    )
    config = SiteAnalyticsConfig.objects.create(site=site, measurement_id="G-12345ABCDE")
    return GA4Setup(user=user, workspace=workspace, site=site, config=config)


def test_gtag_snippet_generation(ga4_setup: GA4Setup) -> None:
    client = APIClient()
    user = ga4_setup.user
    workspace = ga4_setup.workspace
    site = ga4_setup.site

    client.force_authenticate(user=user)
    url = reverse(
        "analytics:tag_snippet", kwargs={"workspace_id": workspace.id, "site_id": site.id}
    )
    resp = client.get(url)

    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["measurement_id"] == "G-12345ABCDE"
    assert "https://www.googletagmanager.com/gtag/js?id=G-12345ABCDE" in data["tag_snippet"]
    assert "gtag('consent', 'default'" in data["tag_snippet"]
    assert data["consent_mode_v2_defaults"]["analytics_storage"] == "denied"
    assert data["consent_mode_v2_defaults"]["ad_storage"] == "denied"
    assert data["consent_mode_v2_defaults"]["ad_user_data"] == "denied"
    assert data["consent_mode_v2_defaults"]["ad_personalization"] == "denied"
    assert data["copy_button_ready"] is True


def test_ga4_oauth_authorize_and_callback(ga4_setup: GA4Setup) -> None:
    client = APIClient()
    user = ga4_setup.user
    workspace = ga4_setup.workspace
    site = ga4_setup.site

    client.force_authenticate(user=user)

    # 1. Authorize
    auth_url = reverse(
        "analytics:ga4_authorize", kwargs={"workspace_id": workspace.id, "site_id": site.id}
    )
    auth_resp = client.get(auth_url)
    assert auth_resp.status_code == status.HTTP_200_OK
    auth_data = auth_resp.json()
    assert "authorization_url" in auth_data
    assert "accounts.google.com" in auth_data["authorization_url"]
    state = auth_data["state"]

    # 2. Callback
    callback_url = reverse(
        "analytics:ga4_callback", kwargs={"workspace_id": workspace.id, "site_id": site.id}
    )
    cb_resp = client.post(
        callback_url, {"code": "mock-auth-code-123", "state": state}, format="json"
    )
    assert cb_resp.status_code == status.HTTP_200_OK

    conn = GA4Connection.objects.get(site=site)
    assert conn.is_active is True
    creds = conn.get_credentials()
    assert creds.get("access_token") == "mock-ga4-access-token"


def test_ga4_properties_and_select(ga4_setup: GA4Setup) -> None:
    client = APIClient()
    user = ga4_setup.user
    workspace = ga4_setup.workspace
    site = ga4_setup.site

    conn = GA4Connection.objects.create(site=site, property_id="pending")
    conn.set_credentials({"access_token": "mock-token"})
    conn.save()

    client.force_authenticate(user=user)

    # List properties
    props_url = reverse(
        "analytics:ga4_properties", kwargs={"workspace_id": workspace.id, "site_id": site.id}
    )
    list_resp = client.get(props_url)
    assert list_resp.status_code == status.HTTP_200_OK
    props = list_resp.json()["properties"]
    assert len(props) > 0
    selected_prop = props[0]["property_id"]

    # Select property
    select_url = reverse(
        "analytics:ga4_property_select", kwargs={"workspace_id": workspace.id, "site_id": site.id}
    )
    sel_resp = client.post(
        select_url,
        {"property_id": selected_prop, "measurement_id": "G-NEWMEASUREMENT"},
        format="json",
    )
    assert sel_resp.status_code == status.HTTP_200_OK

    conn.refresh_from_db()
    assert conn.property_id == selected_prop

    config = SiteAnalyticsConfig.objects.get(site=site)
    assert config.measurement_id == "G-NEWMEASUREMENT"


def test_ga4_disconnect(ga4_setup: GA4Setup) -> None:
    client = APIClient()
    user = ga4_setup.user
    workspace = ga4_setup.workspace
    site = ga4_setup.site

    GA4Connection.objects.create(site=site, property_id="314159")

    client.force_authenticate(user=user)
    disc_url = reverse(
        "analytics:ga4_disconnect", kwargs={"workspace_id": workspace.id, "site_id": site.id}
    )
    resp = client.post(disc_url)
    assert resp.status_code == status.HTTP_200_OK
    assert not GA4Connection.objects.filter(site=site).exists()
