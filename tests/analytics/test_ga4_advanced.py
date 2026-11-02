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


def test_ga4_reporting_and_admin_adapters_direct() -> None:
    from unittest.mock import MagicMock

    import requests

    from apps.analytics.adapters.ga4 import GA4AdminAdapter, GA4ReportingAdapter

    mock_session = MagicMock(spec=requests.Session)

    # 1. GA4ReportingAdapter
    rep_adapter = GA4ReportingAdapter(
        property_id="properties/123456", access_token="mock-token", session=mock_session
    )
    assert rep_adapter.property_id == "123456"

    mock_rep_resp = MagicMock()
    mock_rep_resp.status_code = 200
    mock_rep_resp.json.return_value = {
        "rowCount": 1,
        "metricHeaders": [{"name": "activeUsers"}],
        "dimensionHeaders": [{"name": "country"}],
        "rows": [
            {"dimensionValues": [{"value": "United States"}], "metricValues": [{"value": "42"}]}
        ],
    }
    mock_session.post.return_value = mock_rep_resp

    overview = rep_adapter.get_overview("2026-01-01", "2026-01-30")
    assert overview["status"] == "SUCCESS"
    assert len(overview["rows"]) == 1

    sources = rep_adapter.get_traffic_sources("2026-01-01", "2026-01-30")
    assert sources["status"] == "SUCCESS"

    pages = rep_adapter.get_top_pages("2026-01-01", "2026-01-30")
    assert pages["status"] == "SUCCESS"

    audience = rep_adapter.get_audience("2026-01-01", "2026-01-30")
    assert audience["status"] == "SUCCESS"

    events = rep_adapter.get_events("2026-01-01", "2026-01-30")
    assert events["status"] == "SUCCESS"

    realtime = rep_adapter.get_realtime()
    assert realtime["status"] == "SUCCESS"

    # error handling
    mock_rep_resp.status_code = 403
    mock_rep_resp.text = "Forbidden"
    err = rep_adapter.run_report("2026-01-01", "2026-01-30", ["activeUsers"])
    assert err["status"] == "ERROR"

    mock_session.post.side_effect = requests.RequestException("Conn error")
    exc_res = rep_adapter.run_report("2026-01-01", "2026-01-30", ["activeUsers"])
    assert exc_res["status"] == "ERROR"
    mock_session.post.side_effect = None

    # 2. GA4AdminAdapter
    admin_adapter = GA4AdminAdapter(access_token="mock-token", session=mock_session)
    mock_admin_resp = MagicMock()
    mock_admin_resp.status_code = 200
    mock_admin_resp.json.return_value = {
        "accountSummaries": [
            {
                "displayName": "My Account",
                "propertySummaries": [
                    {"property": "properties/999888", "displayName": "My Web Site"}
                ],
            }
        ]
    }
    mock_session.get.return_value = mock_admin_resp
    summaries = admin_adapter.list_account_summaries()
    assert len(summaries) == 1
    assert summaries[0]["property_id"] == "999888"

    mock_streams_resp = MagicMock()
    mock_streams_resp.status_code = 200
    mock_streams_resp.json.return_value = {
        "dataStreams": [
            {
                "displayName": "Web Stream",
                "type": "WEB_DATA_STREAM",
                "webStreamData": {
                    "measurementId": "G-ADMINSTREAM",
                    "defaultUri": "https://example.com",
                },
            }
        ]
    }
    mock_session.get.return_value = mock_streams_resp
    streams = admin_adapter.list_data_streams("properties/999888")
    assert len(streams) == 1
    assert streams[0]["measurement_id"] == "G-ADMINSTREAM"

    mock_session.get.side_effect = requests.RequestException("Admin error")
    assert admin_adapter.list_account_summaries() == []
    assert admin_adapter.list_data_streams("999888") == []
