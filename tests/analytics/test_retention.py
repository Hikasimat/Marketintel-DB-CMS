"""Tests for analytics retention cleanup, GDPR erasure, and aggregated metrics (ANA-7)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.analytics.models import (
    AnalyticsEvent,
    AnalyticsReportSnapshot,
    DeviceCategory,
    EventType,
    SiteAnalyticsConfig,
)
from apps.analytics.tasks import cleanup_expired_events
from apps.sites.models import Site
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole


@pytest.fixture
def retention_setup(db: None) -> dict[str, object]:
    admin = User.objects.create_user(email="admin@retention.org", password="SecurePassword123!")
    analyst = User.objects.create_user(email="analyst@retention.org", password="SecurePassword123!")

    workspace = Workspace.objects.create(name="Retention Org", slug="retention-org")
    WorkspaceMembership.objects.create(workspace=workspace, user=admin, role=WorkspaceRole.ADMIN)
    WorkspaceMembership.objects.create(
        workspace=workspace, user=analyst, role=WorkspaceRole.ANALYST
    )

    site = Site.objects.create(workspace=workspace, name="Stats Site", slug="stats-site")
    config = SiteAnalyticsConfig.objects.create(
        site=site,
        is_first_party_enabled=True,
        retention_days=30,  # 30 days retention
    )

    return {
        "admin": admin,
        "analyst": analyst,
        "workspace": workspace,
        "site": site,
        "config": config,
    }


@pytest.mark.django_db
def test_retention_cleanup_task(retention_setup: dict[str, object]) -> None:
    site = retention_setup["site"]
    assert isinstance(site, Site)

    now = timezone.now()

    # 1. Event inside 30-day window (should be kept)
    fresh_event = AnalyticsEvent.objects.create(
        site=site,
        event_type=EventType.PAGE_VIEW,
        visitor_id="v-fresh",
        session_id="s-1",
        path="/page-fresh",
        occurred_at=now - timedelta(days=10),
    )

    # 2. Event outside 30-day window (should be pruned)
    expired_event = AnalyticsEvent.objects.create(
        site=site,
        event_type=EventType.PAGE_VIEW,
        visitor_id="v-expired",
        session_id="s-2",
        path="/page-old",
        occurred_at=now - timedelta(days=45),
    )

    # 3. Expired snapshot
    AnalyticsReportSnapshot.objects.create(
        site=site,
        report_type="old_report",
        start_date=(now - timedelta(days=60)).date(),
        end_date=(now - timedelta(days=50)).date(),
        data={},
        expires_at=now - timedelta(days=5),
    )

    # Run cleanup task
    result = cleanup_expired_events()
    assert result["events_deleted"] >= 1
    assert result["snapshots_deleted"] >= 1

    # Verify fresh event retained, expired event deleted
    assert AnalyticsEvent.objects.filter(id=fresh_event.id).exists()
    assert not AnalyticsEvent.objects.filter(id=expired_event.id).exists()


@pytest.mark.django_db
def test_visitor_data_erasure_endpoint(retention_setup: dict[str, object]) -> None:
    client = APIClient()
    admin = retention_setup["admin"]
    analyst = retention_setup["analyst"]
    workspace = retention_setup["workspace"]
    site = retention_setup["site"]
    assert isinstance(workspace, Workspace)
    assert isinstance(site, Site)

    # Create events for visitor A and visitor B
    AnalyticsEvent.objects.create(
        site=site,
        event_type=EventType.PAGE_VIEW,
        visitor_id="visitor-target",
        session_id="s-1",
        path="/p1",
    )
    AnalyticsEvent.objects.create(
        site=site,
        event_type=EventType.CTA_CLICK,
        visitor_id="visitor-target",
        session_id="s-1",
        path="/p2",
    )
    AnalyticsEvent.objects.create(
        site=site,
        event_type=EventType.PAGE_VIEW,
        visitor_id="visitor-other",
        session_id="s-2",
        path="/p1",
    )

    url = reverse(
        "analytics:visitor_erasure",
        kwargs={"workspace_id": workspace.id, "site_id": site.id, "visitor_id": "visitor-target"},
    )

    # 1. Analyst cannot delete visitor data (requires admin)
    client.force_authenticate(user=analyst)
    forbidden_resp = client.delete(url)
    assert forbidden_resp.status_code == status.HTTP_403_FORBIDDEN

    # 2. Admin erases visitor data
    client.force_authenticate(user=admin)
    del_resp = client.delete(url)
    assert del_resp.status_code == status.HTTP_200_OK
    assert del_resp.json()["deleted_events"] == 2

    # Target visitor records removed, other visitor intact
    assert not AnalyticsEvent.objects.filter(site=site, visitor_id="visitor-target").exists()
    assert AnalyticsEvent.objects.filter(site=site, visitor_id="visitor-other").count() == 1


@pytest.mark.django_db
def test_first_party_overview_report(retention_setup: dict[str, object]) -> None:
    client = APIClient()
    analyst = retention_setup["analyst"]
    workspace = retention_setup["workspace"]
    site = retention_setup["site"]
    assert isinstance(workspace, Workspace)
    assert isinstance(site, Site)

    now = timezone.now()
    # Create sample events
    AnalyticsEvent.objects.create(
        site=site,
        event_type=EventType.PAGE_VIEW,
        visitor_id="v-1",
        session_id="s-1",
        path="/home",
        device_category=DeviceCategory.DESKTOP,
        occurred_at=now,
    )
    AnalyticsEvent.objects.create(
        site=site,
        event_type=EventType.PAGE_VIEW,
        visitor_id="v-2",
        session_id="s-2",
        path="/home",
        device_category=DeviceCategory.MOBILE,
        occurred_at=now,
    )
    AnalyticsEvent.objects.create(
        site=site,
        event_type=EventType.CTA_CLICK,
        visitor_id="v-1",
        session_id="s-1",
        path="/pricing",
        device_category=DeviceCategory.DESKTOP,
        occurred_at=now,
    )

    client.force_authenticate(user=analyst)
    url = reverse(
        "analytics:first_party_overview",
        kwargs={"workspace_id": workspace.id, "site_id": site.id},
    )

    resp = client.get(url)
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    summary = data["summary"]
    assert summary["total_events"] == 3
    assert summary["unique_visitors"] == 2
    assert summary["page_views"] == 2
    assert summary["cta_clicks"] == 1

    # Top paths
    assert len(data["top_paths"]) >= 1
    assert data["top_paths"][0]["path"] == "/home"
    assert data["top_paths"][0]["views"] == 2

    # Device breakdown
    assert data["device_breakdown"]["DESKTOP"] == 2
    assert data["device_breakdown"]["MOBILE"] == 1
