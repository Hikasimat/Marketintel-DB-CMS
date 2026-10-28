"""Celery tasks for analytics retention cleanup and cached report snapshots (ANA-7)."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from celery import shared_task
from django.utils import timezone

from apps.analytics.adapters.ga4 import GA4ReportingAdapter
from apps.analytics.models import (
    AnalyticsEvent,
    AnalyticsReportSnapshot,
    SiteAnalyticsConfig,
)
from apps.sites.models import Site

logger = logging.getLogger(__name__)


@shared_task
def cleanup_expired_events() -> dict[str, int]:
    """Prune analytics events exceeding retention windows and expired report snapshots (ANA-7)."""
    now = timezone.now()
    total_events_deleted = 0

    configs = SiteAnalyticsConfig.objects.select_related("site").all()
    for config in configs:
        retention_days = config.retention_days or 90
        cutoff = now - timedelta(days=retention_days)
        deleted_count, _ = AnalyticsEvent.objects.filter(
            site=config.site, occurred_at__lt=cutoff
        ).delete()
        total_events_deleted += deleted_count
        if deleted_count > 0:
            logger.info(
                "Pruned %d expired events for site %s (retention: %d days).",
                deleted_count,
                config.site.slug,
                retention_days,
            )

    # Prune expired cached report snapshots
    snapshots_deleted, _ = AnalyticsReportSnapshot.objects.filter(expires_at__lt=now).delete()

    return {
        "events_deleted": total_events_deleted,
        "snapshots_deleted": snapshots_deleted,
    }


@shared_task
def refresh_ga4_report_snapshot(
    site_id: str,
    report_type: str,
    start_date_str: str,
    end_date_str: str,
) -> dict[str, Any]:
    """Background task to fetch and cache GA4 reporting data."""
    try:
        site = Site.objects.get(id=site_id)
        connection = site.ga4_connection
    except Exception as exc:
        logger.warning("Site or GA4 connection not found for id %s: %s", site_id, exc)
        return {"status": "ERROR", "error": str(exc)}

    if not connection.is_active:
        return {"status": "INACTIVE"}

    credentials = connection.get_credentials()
    access_token = credentials.get("access_token", "")
    if not access_token:
        return {"status": "NO_TOKEN"}

    adapter = GA4ReportingAdapter(
        property_id=connection.property_id,
        access_token=access_token,
    )

    if report_type == "traffic_sources":
        result = adapter.get_traffic_sources(start_date_str, end_date_str)
    elif report_type == "top_pages":
        result = adapter.get_top_pages(start_date_str, end_date_str)
    else:
        result = adapter.get_overview(start_date_str, end_date_str)

    if result.get("status") == "SUCCESS":
        start_d = date.fromisoformat(start_date_str)
        end_d = date.fromisoformat(end_date_str)
        expires_at = timezone.now() + timedelta(hours=6)

        AnalyticsReportSnapshot.objects.update_or_create(
            site=site,
            report_type=report_type,
            start_date=start_d,
            end_date=end_d,
            defaults={"data": result, "expires_at": expires_at},
        )

    return result
