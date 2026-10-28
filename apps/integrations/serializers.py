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

    provider = serializers.ChoiceField(choices=SearchProvider.choices)
    urls = serializers.ListField(
        child=serializers.URLField(),
        min_length=1,
        max_length=10000,
        help_text="List of article or page URLs to submit.",
    )


class UrlInspectionRequestSerializer(serializers.Serializer[Any]):
    """Request serializer for Google Search Console URL Inspection API."""

    url = serializers.URLField(help_text="Fully qualified article or page URL to inspect.")
