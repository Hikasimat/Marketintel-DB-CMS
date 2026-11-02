"""Tests for Google Search Console OAuth, properties, Search Analytics, and sitemaps."""

from __future__ import annotations

import json
from dataclasses import dataclass
from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.integrations.models import ConnectionStatus, SearchEngineConnection, SearchProvider
from apps.sites.models import Domain, Site
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole

pytestmark = pytest.mark.django_db


@dataclass
class GSCSetup:
    user: User
    workspace: Workspace
    site: Site


@pytest.fixture
def gsc_setup() -> GSCSetup:
    user = User.objects.create_user(email="owner@gsctest.com", password="SecurePassword123!")
    workspace = Workspace.objects.create(name="GSC Workspace", slug="gsc-workspace")
    WorkspaceMembership.objects.create(workspace=workspace, user=user, role=WorkspaceRole.OWNER)
    site = Site.objects.create(
        workspace=workspace, name="GSC Site", slug="gsc-site", default_locale="en-US"
    )
    Domain.objects.create(
        site=site, hostname="gsc-site.hikasimat.com", is_primary=True, is_verified=True
    )
    return GSCSetup(user=user, workspace=workspace, site=site)


def test_gsc_oauth_authorize_and_callback(gsc_setup: GSCSetup) -> None:
    client = APIClient()
    user = gsc_setup.user
    workspace = gsc_setup.workspace
    site = gsc_setup.site

    client.force_authenticate(user=user)

    # 1. Authorize URL
    auth_url = reverse(
        "integrations:gsc_authorize", kwargs={"workspace_id": workspace.id, "site_id": site.id}
    )
    auth_resp = client.get(auth_url)
    assert auth_resp.status_code == status.HTTP_200_OK
    data = auth_resp.json()
    assert "authorization_url" in data
    assert "accounts.google.com" in data["authorization_url"]
    state = data["state"]

    # 2. Callback
    cb_url = reverse(
        "integrations:gsc_callback", kwargs={"workspace_id": workspace.id, "site_id": site.id}
    )
    cb_resp = client.post(cb_url, {"code": "mock-code-123", "state": state}, format="json")
    assert cb_resp.status_code == status.HTTP_200_OK

    conn = SearchEngineConnection.objects.get(site=site, provider=SearchProvider.GOOGLE)
    assert conn.status == ConnectionStatus.CONNECTED
    raw = conn.get_credentials()
    tokens = json.loads(raw)
    assert tokens.get("access_token") == "mock-gsc-access-token"


def test_gsc_properties_list_and_select(gsc_setup: GSCSetup) -> None:
    client = APIClient()
    user = gsc_setup.user
    workspace = gsc_setup.workspace
    site = gsc_setup.site

    conn = SearchEngineConnection.objects.create(
        site=site,
        provider=SearchProvider.GOOGLE,
        status=ConnectionStatus.CONNECTED,
    )
    conn.set_credentials(json.dumps({"access_token": "mock-token"}))
    conn.save()

    client.force_authenticate(user=user)

    # 1. List properties
    props_url = reverse(
        "integrations:gsc_properties", kwargs={"workspace_id": workspace.id, "site_id": site.id}
    )
    list_resp = client.get(props_url)
    assert list_resp.status_code == status.HTTP_200_OK
    props = list_resp.json()["properties"]
    assert len(props) > 0

    # 2. Select property
    sel_url = reverse(
        "integrations:gsc_property_select",
        kwargs={"workspace_id": workspace.id, "site_id": site.id},
    )
    sel_resp = client.post(
        sel_url, {"site_url": "sc-domain:gsc-site.hikasimat.com"}, format="json"
    )
    assert sel_resp.status_code == status.HTTP_200_OK

    conn.refresh_from_db()
    assert conn.settings["selected_property"] == "sc-domain:gsc-site.hikasimat.com"


def test_gsc_search_analytics(gsc_setup: GSCSetup) -> None:
    client = APIClient()
    user = gsc_setup.user
    workspace = gsc_setup.workspace
    site = gsc_setup.site

    conn = SearchEngineConnection.objects.create(
        site=site,
        provider=SearchProvider.GOOGLE,
        status=ConnectionStatus.CONNECTED,
        settings={"selected_property": "sc-domain:gsc-site.hikasimat.com"},
    )
    conn.set_credentials(json.dumps({"access_token": "mock-token"}))
    conn.save()

    client.force_authenticate(user=user)

    analytics_url = reverse(
        "integrations:gsc_analytics", kwargs={"workspace_id": workspace.id, "site_id": site.id}
    )

    with patch(
        "apps.integrations.adapters.google.GoogleSearchConsoleAdapter.query_search_analytics"
    ) as mock_query:
        mock_query.return_value = {
            "status": "SUCCESS",
            "site_url": "sc-domain:gsc-site.hikasimat.com",
            "row_count": 2,
            "rows": [
                {
                    "query": "antigravity cms",
                    "clicks": 150,
                    "impressions": 1200,
                    "ctr": 0.125,
                    "position": 2.4,
                },
                {
                    "query": "market intel cms",
                    "clicks": 80,
                    "impressions": 900,
                    "ctr": 0.088,
                    "position": 4.1,
                },
            ],
        }
        resp = client.get(
            analytics_url, {"start_date": "2026-10-01", "end_date": "2026-10-28"}
        )
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["status"] == "SUCCESS"
        assert len(data["rows"]) == 2


def test_gsc_sitemaps_management(gsc_setup: GSCSetup) -> None:
    client = APIClient()
    user = gsc_setup.user
    workspace = gsc_setup.workspace
    site = gsc_setup.site

    conn = SearchEngineConnection.objects.create(
        site=site,
        provider=SearchProvider.GOOGLE,
        status=ConnectionStatus.CONNECTED,
        settings={"selected_property": "https://gsc-site.hikasimat.com/"},
    )
    conn.set_credentials(json.dumps({"access_token": "mock-token"}))
    conn.save()

    client.force_authenticate(user=user)
    sitemaps_url = reverse(
        "integrations:gsc_sitemaps", kwargs={"workspace_id": workspace.id, "site_id": site.id}
    )

    with (
        patch(
            "apps.integrations.adapters.google.GoogleSearchConsoleAdapter.list_sitemaps"
        ) as mock_list,
        patch(
            "apps.integrations.adapters.google.GoogleSearchConsoleAdapter.submit_sitemap"
        ) as mock_submit,
        patch(
            "apps.integrations.adapters.google.GoogleSearchConsoleAdapter.delete_sitemap"
        ) as mock_delete,
    ):
        mock_list.return_value = [
            {"path": "https://gsc-site.hikasimat.com/sitemap.xml", "lastSubmitted": "2026-10-25"}
        ]
        mock_submit.return_value = {
            "status": "SUCCESS",
            "sitemap_url": "https://gsc-site.hikasimat.com/sitemap.xml",
        }
        mock_delete.return_value = {"status": "SUCCESS", "message": "Deleted"}

        # 1. GET
        get_resp = client.get(sitemaps_url)
        assert get_resp.status_code == status.HTTP_200_OK
        assert len(get_resp.json()["sitemaps"]) == 1

        # 2. POST
        post_resp = client.post(
            sitemaps_url,
            {"sitemap_url": "https://gsc-site.hikasimat.com/sitemap.xml"},
            format="json",
        )
        assert post_resp.status_code == status.HTTP_200_OK

        # 3. DELETE
        del_resp = client.delete(
            sitemaps_url,
            {"sitemap_url": "https://gsc-site.hikasimat.com/sitemap.xml"},
            format="json",
        )
        assert del_resp.status_code == status.HTTP_200_OK


def test_gsc_disconnect(gsc_setup: GSCSetup) -> None:
    client = APIClient()
    user = gsc_setup.user
    workspace = gsc_setup.workspace
    site = gsc_setup.site

    SearchEngineConnection.objects.create(
        site=site,
        provider=SearchProvider.GOOGLE,
        status=ConnectionStatus.CONNECTED,
    )

    client.force_authenticate(user=user)
    disc_url = reverse(
        "integrations:gsc_disconnect", kwargs={"workspace_id": workspace.id, "site_id": site.id}
    )
    resp = client.post(disc_url)
    assert resp.status_code == status.HTTP_200_OK
    assert not SearchEngineConnection.objects.filter(
        site=site, provider=SearchProvider.GOOGLE
    ).exists()
