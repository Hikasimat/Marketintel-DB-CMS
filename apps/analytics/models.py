"""Analytics models for GA4 configuration, OAuth credentials, events, and reports."""

from __future__ import annotations

import json
import uuid
from typing import Any, ClassVar

from django.db import models
from django.utils import timezone

from apps.common.crypto import decrypt_secret, encrypt_secret
from apps.sites.models import Site


class EventType(models.TextChoices):
    PAGE_VIEW = "page_view", "Page View"
    CTA_CLICK = "cta_click", "CTA Click"
    FORM_SUBMIT = "form_submit", "Form Submit"


class DeviceCategory(models.TextChoices):
    DESKTOP = "DESKTOP", "Desktop"
    MOBILE = "MOBILE", "Mobile"
    TABLET = "TABLET", "Tablet"
    BOT = "BOT", "Bot"
    UNKNOWN = "UNKNOWN", "Unknown"


class SiteAnalyticsConfig(models.Model):
    """Per-site analytics configuration for GA4/GTM and first-party ingestion (ANA-1, AS-6)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.OneToOneField(Site, on_delete=models.CASCADE, related_name="analytics_config")
    measurement_id = models.CharField(max_length=30, blank=True, default="")
    gtm_container_id = models.CharField(max_length=30, blank=True, default="")
    is_first_party_enabled = models.BooleanField(
        default=False,
        help_text="Toggle first-party privacy-preserving event ingestion (default off).",
    )
    retention_days = models.PositiveIntegerField(
        default=90,
        help_text="Event data retention window in days before automated pruning (7-730 days).",
    )
    require_consent = models.BooleanField(
        default=True,
        help_text="Whether event collection requires explicit visitor consent.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "analytics_site_config"

    def __str__(self) -> str:
        return f"Analytics Config for {self.site.name}"


class GA4Connection(models.Model):
    """Authorized GA4 connection storing encrypted OAuth tokens for Reporting API (ANA-2)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.OneToOneField(Site, on_delete=models.CASCADE, related_name="ga4_connection")
    property_id = models.CharField(
        max_length=50, help_text="Numeric GA4 property ID (e.g. 123456789)."
    )
    encrypted_credentials = models.TextField(
        blank=True,
        default="",
        help_text="AES-256-GCM encrypted OAuth token JSON.",
    )
    is_active = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "analytics_ga4_connection"

    def __str__(self) -> str:
        status = "Active" if self.is_active else "Inactive"
        return f"GA4 Connection ({self.property_id}) for {self.site.name} [{status}]"

    def set_credentials(self, credentials_data: dict[str, Any]) -> None:
        """Encrypt and serialize OAuth credentials dictionary."""
        if not credentials_data:
            self.encrypted_credentials = ""
        else:
            raw_json = json.dumps(credentials_data)
            self.encrypted_credentials = encrypt_secret(raw_json)

    def get_credentials(self) -> dict[str, Any]:
        """Decrypt and deserialize OAuth credentials dictionary."""
        if not self.encrypted_credentials:
            return {}
        try:
            raw_json = decrypt_secret(self.encrypted_credentials)
            return json.loads(raw_json)
        except Exception:
            return {}


class AnalyticsEvent(models.Model):
    """Privacy-preserving first-party analytics event (ANA-4, ANA-5).

    Privacy Guarantee:
    - Zero raw IP addresses are ever stored or column-defined (ANA-5).
    - User-Agent is coarsened to DeviceCategory and BrowserFamily.
    - Pseudonymous IDs only (visitor_id, session_id).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="analytics_events")
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    visitor_id = models.CharField(max_length=64, db_index=True)
    session_id = models.CharField(max_length=64, db_index=True)
    path = models.CharField(max_length=500, db_index=True)
    properties = models.JSONField(default=dict)
    device_category = models.CharField(
        max_length=20, choices=DeviceCategory.choices, default=DeviceCategory.UNKNOWN
    )
    browser_family = models.CharField(max_length=20, default="OTHER")
    consent_basis = models.CharField(max_length=50, default="EXPLICIT_CONSENT")
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "analytics_event"
        ordering = ("-occurred_at",)
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["site", "occurred_at"]),
            models.Index(fields=["site", "event_type", "occurred_at"]),
            models.Index(fields=["site", "visitor_id"]),
            models.Index(fields=["site", "path"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.event_type} on {self.site.name}:{self.path} at {self.occurred_at.isoformat()}"
        )


class AnalyticsReportSnapshot(models.Model):
    """Cached analytics report snapshots to avoid external API quotas (ANA-3)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="analytics_snapshots")
    report_type = models.CharField(max_length=50)
    start_date = models.DateField()
    end_date = models.DateField()
    data = models.JSONField(default=dict)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "analytics_report_snapshot"
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["site", "report_type", "start_date", "end_date"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.report_type} ({self.start_date} to {self.end_date}) for {self.site.name}"
