"""Serializers for Site and Domain management."""

from __future__ import annotations

from typing import Any, ClassVar

from rest_framework import serializers

from apps.sites.models import Domain, Site
from apps.sites.validators import validate_hostname


class DomainSerializer(serializers.ModelSerializer[Domain]):
    dns_verification_record = serializers.SerializerMethodField()

    class Meta:
        model = Domain
        fields = (
            "id",
            "hostname",
            "is_primary",
            "verification_token",
            "is_verified",
            "verified_at",
            "ssl_status",
            "dns_verification_record",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "verification_token",
            "is_verified",
            "verified_at",
            "ssl_status",
            "dns_verification_record",
            "created_at",
            "updated_at",
        )

    def get_dns_verification_record(self, obj: Domain) -> dict[str, str]:
        return {
            "type": "TXT",
            "name": f"_cms-verify.{obj.hostname}",
            "value": f"cms-verify-token={obj.verification_token}",
        }


class DomainCreateSerializer(serializers.ModelSerializer[Domain]):
    class Meta:
        model = Domain
        fields = ("hostname", "is_primary")

    def validate_hostname(self, value: str) -> str:
        return validate_hostname(value)


class DomainVerifyRequestSerializer(serializers.Serializer[Any]):
    simulate_success = serializers.BooleanField(required=False, default=True)


class SiteSerializer(serializers.ModelSerializer[Site]):
    primary_domain = serializers.SerializerMethodField()

    class Meta:
        model = Site
        fields = (
            "id",
            "name",
            "slug",
            "default_locale",
            "theme_config",
            "settings",
            "allowed_origins",
            "is_active",
            "primary_domain",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "primary_domain", "created_at", "updated_at")

    def get_primary_domain(self, obj: Site) -> str | None:
        primary = obj.domains.filter(is_primary=True).first()
        return primary.hostname if primary else None


class SiteCreateSerializer(serializers.ModelSerializer[Site]):
    class Meta:
        model = Site
        fields = (
            "name",
            "slug",
            "default_locale",
            "theme_config",
            "settings",
            "allowed_origins",
            "is_active",
        )
        extra_kwargs: ClassVar[dict[str, Any]] = {"slug": {"required": False}}
