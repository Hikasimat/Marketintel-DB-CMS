"""Serializers for search engine integrations and indexing logs."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.integrations.models import (
    ConnectionStatus,
    IndexNowKey,
    IndexSubmissionLog,
    SearchEngineConnection,
    SearchProvider,
)


class SearchEngineConnectionSerializer(serializers.ModelSerializer[SearchEngineConnection]):
    """Serializer for search engine API connections with write-only credentials (SEC-3)."""

    credentials = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        help_text="Raw API key or access token. Will be encrypted at rest with AES-256-GCM.",
    )

    class Meta:
        model = SearchEngineConnection
        fields = (
            "id",
            "provider",
            "status",
            "last_synced_at",
            "error_message",
            "settings",
            "credentials",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "status",
            "last_synced_at",
            "error_message",
            "created_at",
            "updated_at",
        )

    def create(self, validated_data: dict[str, Any]) -> SearchEngineConnection:
        credentials = validated_data.pop("credentials", "")
        instance = SearchEngineConnection(**validated_data)
        if credentials:
            instance.set_credentials(credentials)
            instance.status = ConnectionStatus.CONNECTED
        instance.save()
        return instance

    def update(
        self, instance: SearchEngineConnection, validated_data: dict[str, Any]
    ) -> SearchEngineConnection:
        credentials = validated_data.pop("credentials", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if credentials is not None:
            instance.set_credentials(credentials)
            if credentials:
                instance.status = ConnectionStatus.CONNECTED
                instance.error_message = ""
        instance.save()
        return instance


class GoogleSearchConsoleCallbackSerializer(serializers.Serializer[Any]):
    """Serializer for OAuth callback receiving code and state."""

    code = serializers.CharField()
    state = serializers.CharField()


class GoogleSearchConsolePropertySelectSerializer(serializers.Serializer[Any]):
    """Serializer for associating a GSC siteUrl (domain or prefix property) with a CMS site."""

    site_url = serializers.CharField(
        help_text="Search Console property identifier (e.g. sc-domain:example.com or https://example.com/)."
    )


class GoogleSearchConsoleAnalyticsRequestSerializer(serializers.Serializer[Any]):
    """Query parameter serializer for Search Analytics performance reporting."""

    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    dimensions = serializers.ListField(
        child=serializers.ChoiceField(choices=["query", "page", "country", "device", "date"]),
        required=False,
        default=list,
    )
    row_limit = serializers.IntegerField(required=False, default=1000, min_value=1, max_value=25000)
    search_type = serializers.ChoiceField(
        choices=["web", "image", "video", "news", "discover", "googleNews"],
        default="web",
    )


class GoogleSearchConsoleSitemapSubmitSerializer(serializers.Serializer[Any]):
    """Serializer for submitting or deleting a sitemap in Google Search Console."""

    sitemap_url = serializers.URLField()


class IndexNowKeySerializer(serializers.ModelSerializer[IndexNowKey]):
    """Serializer for IndexNow key hosted verification file."""

    class Meta:
        model = IndexNowKey
        fields = (
            "id",
            "key",
            "key_location",
            "is_verified",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "key",
            "key_location",
            "is_verified",
            "created_at",
            "updated_at",
        )


class IndexSubmissionLogSerializer(serializers.ModelSerializer[IndexSubmissionLog]):
    """Serializer for indexing submission logs and audit trail."""

    class Meta:
        model = IndexSubmissionLog
        fields = (
            "id",
            "provider",
            "urls",
            "idempotency_key",
            "status",
            "response_code",
            "response_body",
            "retry_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ManualSubmissionSerializer(serializers.Serializer[Any]):
    """Request serializer for manual URL batch submission to search engines."""

    provider = serializers.CharField()
    urls = serializers.ListField(
        child=serializers.URLField(),
        min_length=1,
        max_length=10000,
        help_text="List of article or page URLs to submit.",
    )

    def validate_provider(self, value: str) -> str:
        val_upper = str(value).strip().upper()
        if val_upper not in SearchProvider.values:
            valid = ", ".join(SearchProvider.values)
            raise serializers.ValidationError(f"Invalid provider '{value}'. Valid choices: {valid}")
        return val_upper


class UrlInspectionRequestSerializer(serializers.Serializer[Any]):
    """Request serializer for Google Search Console URL Inspection API."""

    url = serializers.URLField(help_text="Fully qualified article or page URL to inspect.")
