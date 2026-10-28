"""Tests for GA4 Data API reporting adapter, report snapshots, and caching (ANA-3)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.analytics.adapters.ga4 import GA4ReportingAdapter
from apps.analytics.models import AnalyticsReportSnapshot, GA4Connection
from apps.analytics.tasks import refresh_ga4_report_snapshot
from apps.sites.models import Site
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole


@pytest.fixture
def reports_setup(db: None) -> dict[str, object]:
    user = User.objects.create_user(email="analyst@reports.org", password="SecurePassword123!")
    workspace = Workspace.objects.create(name="Reports Org", slug="reports-org")
    WorkspaceMembership.objects.create(workspace=workspace, user=user, role=WorkspaceRole.ANALYST)

    site = Site.objects.create(
        workspace=workspace, name="Analytics Portal", slug="analytics-portal"
    )

    conn = GA4Connection.objects.create(site=site, property_id="123456789")
    conn.set_credentials({"access_token": "valid-ga4-token"})
    conn.save()

    return {
        "user": user,
        "workspace": workspace,
        "site": site,
        "conn": conn,
    }


def test_ga4_adapter_run_report_success() -> None:
    session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "dimensionHeaders": [{"name": "pagePath"}],
        "metricHeaders": [{"name": "screenPageViews"}],
        "rows": [
            {
                "dimensionValues": [{"value": "/blog/post-1"}],
                "metricValues": [{"value": "1250"}],
            }
        ],
        "rowCount": 1,
    }
    session.post.return_value = mock_resp

    adapter = GA4ReportingAdapter(
        property_id="123456789",
        access_token="test-token",  # nosec B106
        session=session,
    )
    res = adapter.run_report(
        start_date="2026-01-01",
        end_date="2026-01-31",
        metrics=["screenPageViews"],
        dimensions=["pagePath"],
    )

    assert res["status"] == "SUCCESS"
    assert res["row_count"] == 1
    assert len(res["rows"]) == 1
    assert res["rows"][0]["pagePath"] == "/blog/post-1"
    assert res["rows"][0]["screenPageViews"] == "1250"


def test_ga4_adapter_error_handling() -> None:
    session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.text = "Quota exceeded"
    session.post.return_value = mock_resp

    adapter = GA4ReportingAdapter(
        property_id="123456789",
        access_token="test-token",  # nosec B106
        session=session,
    )
    res = adapter.get_overview("2026-01-01", "2026-01-31")

    assert res["status"] == "ERROR"
    assert res["code"] == 429
    assert res["error"] == "Quota exceeded"


@pytest.mark.django_db
def test_ga4_report_api_and_caching(reports_setup: dict[str, object]) -> None:
    client = APIClient()
    user = reports_setup["user"]
    workspace = reports_setup["workspace"]
    site = reports_setup["site"]
    assert isinstance(workspace, Workspace)
    assert isinstance(site, Site)

    client.force_authenticate(user=user)
    url = reverse(
        "analytics:ga4_reports",
        kwargs={"workspace_id": workspace.id, "site_id": site.id},
    )

    # 1. Invalid date range rejected
    bad_range = client.get(url, {"start_date": "2026-02-01", "end_date": "2026-01-01"})
    assert bad_range.status_code == status.HTTP_400_BAD_REQUEST

    # 2. Exceeds 365 days rejected
    exceeded = client.get(url, {"start_date": "2024-01-01", "end_date": "2026-01-01"})
    assert exceeded.status_code == status.HTTP_400_BAD_REQUEST

    # 3. Live report invocation
    with patch("apps.analytics.views.GA4ReportingAdapter.get_overview") as mock_overview:
        mock_overview.return_value = {
            "status": "SUCCESS",
            "property_id": "123456789",
            "rows": [{"activeUsers": "500", "sessions": "750"}],
        }

        resp = client.get(
            url,
            {
                "report_type": "overview",
                "start_date": "2026-01-01",
                "end_date": "2026-01-10",
                "use_cache": False,
            },
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["status"] == "SUCCESS"
        assert resp.json()["cached"] is False
        assert mock_overview.called

        # 4. Subsequent request served from cache
        mock_overview.reset_mock()
        cached_resp = client.get(
            url,
            {
                "report_type": "overview",
                "start_date": "2026-01-01",
                "end_date": "2026-01-10",
                "use_cache": True,
            },
        )
        assert cached_resp.status_code == status.HTTP_200_OK
        assert cached_resp.json()["cached"] is True
        # Upstream adapter was not called because snapshot was used
        assert not mock_overview.called


@pytest.mark.django_db
def test_refresh_ga4_report_snapshot_task(reports_setup: dict[str, object]) -> None:
    site = reports_setup["site"]
    assert isinstance(site, Site)

    with patch("apps.analytics.tasks.GA4ReportingAdapter.get_overview") as mock_overview:
        mock_overview.return_value = {
            "status": "SUCCESS",
            "rows": [{"activeUsers": "1000"}],
        }

        res = refresh_ga4_report_snapshot(
            site_id=str(site.id),
            report_type="overview",
            start_date_str="2026-01-01",
            end_date_str="2026-01-15",
        )
        assert res["status"] == "SUCCESS"

        snapshot = AnalyticsReportSnapshot.objects.filter(site=site, report_type="overview").first()
        assert snapshot is not None
        assert snapshot.data["rows"][0]["activeUsers"] == "1000"
