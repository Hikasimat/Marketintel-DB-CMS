"""Serializers for analytics configurations, GA4 connections, and event ingestion."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.analytics.models import (
    EventType,
    GA4Connection,
    SiteAnalyticsConfig,
)
from apps.analytics.validators import (
    validate_ga4_property_id,
    validate_gtm_container_id,
    validate_measurement_id,
)


class SiteAnalyticsConfigSerializer(serializers.ModelSerializer[SiteAnalyticsConfig]):
    """Serializer for managing site analytics settings (ANA-1)."""

    class Meta:
        model = SiteAnalyticsConfig
        fields = (
            "id",
            "measurement_id",
            "gtm_container_id",
            "is_first_party_enabled",
            "retention_days",
            "require_consent",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_measurement_id(self, value: str) -> str:
        return validate_measurement_id(value)

    def validate_gtm_container_id(self, value: str) -> str:
        return validate_gtm_container_id(value)

    def validate_retention_days(self, value: int) -> int:
        if value < 7 or value > 730:
            raise serializers.ValidationError("Retention period must be between 7 and 730 days.")
        return value


class PublicAnalyticsConfigSerializer(serializers.ModelSerializer[SiteAnalyticsConfig]):
    """Public serializer delivering only non-secret IDs for browser frontend loaders (ANA-1)."""

    class Meta:
        model = SiteAnalyticsConfig
        fields = (
            "measurement_id",
            "gtm_container_id",
            "is_first_party_enabled",
            "require_consent",
        )
        read_only_fields = fields


class GA4ConnectionSerializer(serializers.ModelSerializer[GA4Connection]):
    """Serializer for GA4 authorized connection with write-only credentials (ANA-2)."""

    credentials = serializers.JSONField(
        write_only=True,
        required=False,
        help_text="OAuth tokens and credentials dictionary. Encrypted with AES-256-GCM at rest.",
    )

    class Meta:
        model = GA4Connection
        fields = (
            "id",
            "property_id",
            "is_active",
            "last_synced_at",
            "last_error",
            "credentials",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "last_synced_at",
            "last_error",
            "created_at",
            "updated_at",
        )

    def validate_property_id(self, value: str) -> str:
        return validate_ga4_property_id(value)

    def create(self, validated_data: dict[str, Any]) -> GA4Connection:
        creds = validated_data.pop("credentials", None)
        conn = GA4Connection(**validated_data)
        if creds:
            conn.set_credentials(creds)
        conn.save()
        return conn

    def update(self, instance: GA4Connection, validated_data: dict[str, Any]) -> GA4Connection:
        creds = validated_data.pop("credentials", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if creds is not None:
            instance.set_credentials(creds)
        instance.save()
        return instance


class EventIngestSerializer(serializers.Serializer[Any]):
    """Serializer for public first-party event ingestion (ANA-4, ANA-6)."""

    event_type = serializers.ChoiceField(choices=EventType.choices)
    visitor_id = serializers.CharField(max_length=64)
    session_id = serializers.CharField(max_length=64)
    path = serializers.CharField(max_length=500)
    properties = serializers.DictField(
        required=False, default=dict, help_text="Allowlisted properties dictionary."
    )
    consent_granted = serializers.BooleanField(required=False, default=False)


class GA4ReportRequestSerializer(serializers.Serializer[Any]):
    """Query parameter serializer for GA4 Data API reports (ANA-3)."""

    report_type = serializers.ChoiceField(
        choices=["overview", "traffic_sources", "top_pages"], default="overview"
    )
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    use_cache = serializers.BooleanField(required=False, default=True)
