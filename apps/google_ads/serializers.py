"""Serializers for Google Ads connections, OAuth exchange, GAQL queries, and mutations."""

from __future__ import annotations

import datetime
from typing import Any, ClassVar

from rest_framework import serializers

from apps.google_ads.models import GoogleAdsCampaignAuditLog, GoogleAdsConnection


class GoogleAdsConnectionSerializer(serializers.ModelSerializer[GoogleAdsConnection]):
    has_credentials = serializers.SerializerMethodField()
    has_developer_token = serializers.SerializerMethodField()

    class Meta:
        model = GoogleAdsConnection
        fields: ClassVar[list[str]] = [
            "id",
            "workspace",
            "customer_id",
            "manager_customer_id",
            "is_active",
            "status",
            "last_synced_at",
            "last_error",
            "has_credentials",
            "has_developer_token",
            "created_at",
            "updated_at",
        ]
        read_only_fields: ClassVar[list[str]] = [
            "id",
            "workspace",
            "is_active",
            "status",
            "last_synced_at",
            "last_error",
            "has_credentials",
            "has_developer_token",
            "created_at",
            "updated_at",
        ]

    def get_has_credentials(self, obj: GoogleAdsConnection) -> bool:
        return bool(obj.encrypted_credentials)

    def get_has_developer_token(self, obj: GoogleAdsConnection) -> bool:
        return bool(obj.encrypted_developer_token)


class GoogleAdsAuthorizeSerializer(serializers.Serializer[Any]):
    redirect_uri = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Custom redirect URI matching Google Cloud OAuth consent configuration.",
    )


class GoogleAdsCallbackSerializer(serializers.Serializer[Any]):
    code = serializers.CharField(required=True, help_text="Authorization code returned by Google.")
    redirect_uri = serializers.CharField(
        required=True, help_text="Exact redirect URI used in authorize."
    )
    developer_token = serializers.CharField(
        required=False, allow_blank=True, help_text="Optional developer token to save."
    )


class GoogleAdsCustomerSelectSerializer(serializers.Serializer[Any]):
    customer_id = serializers.CharField(
        required=True, help_text="Google Ads customer ID (e.g. 123-456-7890 or 1234567890)."
    )
    manager_customer_id = serializers.CharField(
        required=False, allow_blank=True, default="", help_text="Optional manager account CID."
    )
    developer_token = serializers.CharField(
        required=False, allow_blank=True, default="", help_text="Optional developer token update."
    )

    def validate_customer_id(self, value: str) -> str:
        clean = value.replace("-", "").strip()
        if not clean.isdigit() or len(clean) != 10:
            raise serializers.ValidationError("Customer ID must be a 10-digit number.")
        return value.strip()


class GoogleAdsDateRangeSerializer(serializers.Serializer[Any]):
    start_date = serializers.DateField(
        required=False,
        help_text="Start date (YYYY-MM-DD). Defaults to 30 days ago.",
    )
    end_date = serializers.DateField(
        required=False,
        help_text="End date (YYYY-MM-DD). Defaults to today.",
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        today = datetime.date.today()
        start = attrs.get("start_date") or (today - datetime.timedelta(days=30))
        end = attrs.get("end_date") or today
        if start > end:
            raise serializers.ValidationError("start_date cannot be after end_date.")
        attrs["start_date"] = start
        attrs["end_date"] = end
        return attrs


class GoogleAdsCampaignActionSerializer(serializers.Serializer[Any]):
    confirm = serializers.BooleanField(
        required=True,
        help_text="Must explicitly confirm mutation action (True).",
    )
    campaign_name = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Optional name for audit log recording.",
    )

    def validate_confirm(self, value: bool) -> bool:
        if value is not True:
            raise serializers.ValidationError("Explicit confirmation (confirm=True) is required.")
        return value


class GoogleAdsBudgetUpdateSerializer(serializers.Serializer[Any]):
    budget_resource_name = serializers.CharField(
        required=True,
        help_text="Resource name of the campaign budget (e.g. customers/123/campaignBudgets/456).",
    )
    amount_micros = serializers.IntegerField(
        required=True,
        min_value=1,
        help_text="New budget amount in micros (e.g. $10.00 = 10,000,000 micros).",
    )
    campaign_id = serializers.CharField(
        required=True,
        help_text="Associated campaign ID for audit log.",
    )
    campaign_name = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Optional campaign name for audit log.",
    )
    confirm = serializers.BooleanField(
        required=True,
        help_text="Must explicitly confirm budget mutation (True).",
    )

    def validate_confirm(self, value: bool) -> bool:
        if value is not True:
            raise serializers.ValidationError("Explicit confirmation (confirm=True) is required.")
        return value


class GoogleAdsCampaignAuditLogSerializer(serializers.ModelSerializer[GoogleAdsCampaignAuditLog]):
    performed_by_email = serializers.SerializerMethodField()

    class Meta:
        model = GoogleAdsCampaignAuditLog
        fields: ClassVar[list[str]] = [
            "id",
            "connection",
            "action",
            "campaign_id",
            "campaign_name",
            "performed_by",
            "performed_by_email",
            "details",
            "created_at",
        ]
        read_only_fields = fields

    def get_performed_by_email(self, obj: GoogleAdsCampaignAuditLog) -> str | None:
        return obj.performed_by.email if obj.performed_by else None
