"""Analytics services for event ingestion, database aggregation, and GDPR data erasure."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from django.db import models
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.analytics.models import AnalyticsEvent, EventType, SiteAnalyticsConfig
from apps.analytics.validators import coarsen_user_agent, validate_event_properties
from apps.sites.models import Site


def ingest_first_party_event(
    site: Site,
    event_type: str,
    visitor_id: str,
    session_id: str,
    path: str,
    properties: dict[str, Any] | None = None,
    user_agent: str = "",
    consent_granted: bool = False,
) -> AnalyticsEvent:
    """Ingest a privacy-preserving first-party analytics event (ANA-4, ANA-5, ANA-6)."""
    try:
        config = site.analytics_config
    except SiteAnalyticsConfig.DoesNotExist:
        config = SiteAnalyticsConfig.objects.create(site=site)

    if not config.is_first_party_enabled:
        raise ValidationError("First-party analytics event ingestion is disabled for this site.")

    if config.require_consent and not consent_granted:
        raise PermissionDenied(
            "Explicit visitor consent is required for analytics event ingestion."
        )

    if not visitor_id or len(visitor_id) > 64:
        raise ValidationError(
            "Invalid visitor_id. Expected pseudonymous identifier up to 64 chars."
        )

    if not session_id or len(session_id) > 64:
        raise ValidationError("Invalid session_id. Expected identifier up to 64 chars.")

    if not path:
        raise ValidationError("Path is required.")

    # Validate allowlisted properties and sanitize PII/HTML
    cleaned_props = validate_event_properties(event_type, properties or {})

    # Coarsen User-Agent to device category and browser family (ANA-5)
    device_category, browser_family = coarsen_user_agent(user_agent)

    return AnalyticsEvent.objects.create(
        site=site,
        event_type=event_type,
        visitor_id=visitor_id,
        session_id=session_id,
        path=path[:500],
        properties=cleaned_props,
        device_category=device_category,
        browser_family=browser_family,
        consent_basis="EXPLICIT_CONSENT" if consent_granted else "LEGITIMATE_INTEREST",
    )


def get_first_party_metrics(
    site: Site,
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    """Calculate aggregated metrics and time-series rollups for site (ANA-7)."""
    start_dt = timezone.make_aware(datetime.combine(start_date, time.min))
    end_dt = timezone.make_aware(datetime.combine(end_date, time.max))

    qs = AnalyticsEvent.objects.filter(site=site, occurred_at__range=(start_dt, end_dt))

    # Overall totals
    total_events = qs.count()
    unique_visitors = qs.values("visitor_id").distinct().count()
    page_views = qs.filter(event_type=EventType.PAGE_VIEW).count()
    cta_clicks = qs.filter(event_type=EventType.CTA_CLICK).count()
    form_submits = qs.filter(event_type=EventType.FORM_SUBMIT).count()

    # Daily time-series breakdown
    daily_qs = (
        qs.annotate(day=TruncDate("occurred_at"))
        .values("day")
        .annotate(
            total=Count("id"),
            visitors=Count("visitor_id", distinct=True),
            page_views=Count("id", filter=models.Q(event_type=EventType.PAGE_VIEW)),
        )
        .order_by("day")
    )
    daily_series = [
        {
            "date": item["day"].isoformat() if item["day"] else "",
            "total_events": item["total"],
            "unique_visitors": item["visitors"],
            "page_views": item["page_views"],
        }
        for item in daily_qs
    ]

    # Top paths (up to 10)
    top_paths_qs = (
        qs.filter(event_type=EventType.PAGE_VIEW)
        .values("path")
        .annotate(views=Count("id"))
        .order_by("-views")[:10]
    )
    top_paths = [{"path": item["path"], "views": item["views"]} for item in top_paths_qs]

    # Device breakdown
    device_qs = qs.values("device_category").annotate(count=Count("id")).order_by("-count")
    device_breakdown = {item["device_category"]: item["count"] for item in device_qs}

    return {
        "site_id": str(site.id),
        "date_range": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "summary": {
            "total_events": total_events,
            "unique_visitors": unique_visitors,
            "page_views": page_views,
            "cta_clicks": cta_clicks,
            "form_submits": form_submits,
        },
        "daily_series": daily_series,
        "top_paths": top_paths,
        "device_breakdown": device_breakdown,
    }


def erase_visitor_data(site: Site, visitor_id: str) -> int:
    """Erase all recorded events for a given visitor ID (GDPR Art. 17 right to erasure)."""
    if not visitor_id:
        return 0
    deleted_count, _ = AnalyticsEvent.objects.filter(site=site, visitor_id=visitor_id).delete()
    return deleted_count
