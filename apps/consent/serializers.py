"""Serializers for consent management and public browser contracts."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.consent.models import (
    ConsentRecord,
    ConsentType,
    JurisdictionMode,
    PrivacyPolicyVersion,
    SiteConsentConfig,
)
from apps.consent.validators import (
    validate_custom_categories_definition,
    validate_policy_version_string,
    validate_visitor_id,
)


class PrivacyPolicyVersionSerializer(serializers.ModelSerializer[PrivacyPolicyVersion]):
    """Serializer for privacy policy versions."""

    site_id = serializers.UUIDField(source="site.id", read_only=True)

    class Meta:
        model = PrivacyPolicyVersion
        fields = (
            "id",
            "site_id",
            "version",
            "title",
            "summary",
            "body",
            "is_active",
            "effective_date",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "site_id", "is_active", "created_at", "updated_at")

    def validate_version(self, value: str) -> str:
        validate_policy_version_string(value)
        return value


class PrivacyPolicyVersionCreateSerializer(serializers.ModelSerializer[PrivacyPolicyVersion]):
    """Serializer for creating a new privacy policy version."""

    activate_now = serializers.BooleanField(
        default=False,
        required=False,
        write_only=True,
        help_text="Whether to immediately activate this policy version upon creation.",
    )

    class Meta:
        model = PrivacyPolicyVersion
        fields = (
            "id",
            "version",
            "title",
            "summary",
            "body",
            "effective_date",
            "activate_now",
            "is_active",
            "created_at",
        )
        read_only_fields = ("id", "is_active", "created_at")

    def validate_version(self, value: str) -> str:
        validate_policy_version_string(value)
        return value


class SiteConsentConfigSerializer(serializers.ModelSerializer[SiteConsentConfig]):
    """Serializer for per-site consent configuration (CON-1)."""

    site_id = serializers.UUIDField(source="site.id", read_only=True)
    all_categories = serializers.SerializerMethodField()
    active_policy_version_detail = PrivacyPolicyVersionSerializer(
        source="active_policy_version", read_only=True
    )

    class Meta:
        model = SiteConsentConfig
        fields = (
            "id",
            "site_id",
            "is_enabled",
            "jurisdiction_mode",
            "retention_days",
            "cookie_domain",
            "active_policy_version",
            "active_policy_version_detail",
            "categories",
            "all_categories",
            "gcm_enabled",
            "gcm_default_analytics_storage",
            "gcm_default_ad_storage",
            "gcm_default_ad_user_data",
            "gcm_default_ad_personalization",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "site_id", "created_at", "updated_at")

    def get_all_categories(self, obj: SiteConsentConfig) -> dict[str, Any]:
        return obj.get_all_categories()

    def validate_categories(self, value: Any) -> Any:
        if value:
            validate_custom_categories_definition(value)
        return value

    def validate_retention_days(self, value: int) -> int:
        if value < 30 or value > 1095:
            raise serializers.ValidationError("Retention days must be between 30 and 1095 days.")
        return value


class ConsentRecordSerializer(serializers.ModelSerializer[ConsentRecord]):
    """Serializer for consent audit trail records (CON-3, CON-6)."""

    site_id = serializers.UUIDField(source="site.id", read_only=True)

    class Meta:
        model = ConsentRecord
        fields = (
            "id",
            "site_id",
            "visitor_id",
            "policy_version_string",
            "categories",
            "status",
            "consent_type",
            "recorded_at",
            "withdrawn_at",
            "expires_at",
        )
        read_only_fields = fields


class PublicBannerConfigSerializer(serializers.Serializer[Any]):
    """Contract serializer for browser/SDK consent banner loading (CON-2)."""

    is_enabled = serializers.BooleanField()
    jurisdiction_mode = serializers.ChoiceField(choices=JurisdictionMode.choices)
    cookie_domain = serializers.CharField(allow_blank=True)
    active_policy = serializers.DictField(allow_null=True)
    categories = serializers.DictField()
    default_states = serializers.DictField()
    gcm_enabled = serializers.BooleanField()
    gcm_defaults = serializers.DictField()


class PublicConsentSubmitSerializer(serializers.Serializer[Any]):
    """Payload serializer for visitor submitting consent choices (CON-3)."""

    visitor_id = serializers.CharField(max_length=128)
    policy_version = serializers.CharField(
        max_length=50, required=False, allow_blank=True, default=""
    )
    categories = serializers.DictField(child=serializers.BooleanField())
    consent_type = serializers.CharField(
        required=False,
        default=ConsentType.EXPLICIT_OPT_IN,
    )

    def validate_consent_type(self, value: str) -> str:
        val_upper = str(value).strip().upper()
        if val_upper in ("OPT_IN", "EXPLICIT_OPT_IN"):
            return ConsentType.EXPLICIT_OPT_IN
        if val_upper in ("OPT_OUT", "OPTOUT"):
            return ConsentType.OPT_OUT
        if val_upper in (ConsentType.IMPLICIT_NECESSARY_ONLY, "NECESSARY"):
            return ConsentType.IMPLICIT_NECESSARY_ONLY
        valid = ", ".join(
            [ConsentType.EXPLICIT_OPT_IN, ConsentType.OPT_OUT, ConsentType.IMPLICIT_NECESSARY_ONLY]
        )
        raise serializers.ValidationError(f"Invalid consent_type '{value}'. Valid: {valid}")

    def validate_visitor_id(self, value: str) -> str:
        validate_visitor_id(value)
        return value


class PublicConsentWithdrawSerializer(serializers.Serializer[Any]):
    """Payload serializer for visitor withdrawing all consent (CON-4)."""

    visitor_id = serializers.CharField(max_length=128)

    def validate_visitor_id(self, value: str) -> str:
        validate_visitor_id(value)
        return value


class PublicConsentStatusSerializer(serializers.Serializer[Any]):
    """Response serializer for public visitor consent status inquiry."""

    has_consent_record = serializers.BooleanField()
    record_id = serializers.CharField(required=False)
    status = serializers.CharField()
    categories = serializers.DictField()
    recorded_at = serializers.CharField(required=False)
    expires_at = serializers.CharField(required=False)
    policy_version = serializers.CharField(allow_null=True)
    requires_reconsent = serializers.BooleanField()
    is_withdrawn = serializers.BooleanField()


class ConsentSummarySerializer(serializers.Serializer[Any]):
    """Aggregated consent summary response."""

    total_decisions = serializers.IntegerField()
    granted_count = serializers.IntegerField()
    partially_granted_count = serializers.IntegerField()
    denied_count = serializers.IntegerField()
    withdrawn_count = serializers.IntegerField()
    category_acceptance_rates = serializers.DictField(child=serializers.FloatField())
