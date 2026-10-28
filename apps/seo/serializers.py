"""Serializers for SEO settings, article metadata, redirects, and audits."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.seo.models import ArticleSEO, RedirectRule, RedirectStatusCode, SiteSEOSettings
from apps.seo.validators import (
    validate_canonical_url,
    validate_jsonld_schema,
    validate_redirect_rule,
)


class SiteSEOSettingsSerializer(serializers.ModelSerializer[SiteSEOSettings]):
    title_suffix = serializers.CharField(
        max_length=100, required=False, allow_blank=True, trim_whitespace=False
    )

    class Meta:
        model = SiteSEOSettings
        fields = (
            "id",
            "title_suffix",
            "default_meta_description",
            "default_robots_index",
            "default_robots_follow",
            "default_og_image_url",
            "custom_robots_txt",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class ArticleSEOSerializer(serializers.ModelSerializer[ArticleSEO]):
    class Meta:
        model = ArticleSEO
        fields = (
            "id",
            "meta_title",
            "meta_description",
            "canonical_url",
            "robots_index",
            "robots_follow",
            "og_title",
            "og_description",
            "og_image_url",
            "twitter_card",
            "jsonld_schema",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_canonical_url(self, value: str) -> str:
        article = self.context.get("article")
        if article and value:
            return validate_canonical_url(value, article.site)
        return value

    def validate_jsonld_schema(self, value: dict[str, Any]) -> dict[str, Any]:
        return validate_jsonld_schema(value)


class RedirectRuleSerializer(serializers.ModelSerializer[RedirectRule]):
    status_code = serializers.ChoiceField(
        choices=RedirectStatusCode.choices, default=RedirectStatusCode.MOVED_PERMANENTLY
    )

    class Meta:
        model = RedirectRule
        fields = (
            "id",
            "source_path",
            "target_url",
            "status_code",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        site = self.context.get("site")
        if not site:
            return attrs

        src = attrs.get("source_path", getattr(self.instance, "source_path", ""))
        target = attrs.get("target_url", getattr(self.instance, "target_url", ""))
        rule_id = getattr(self.instance, "id", None)

        validated_src, validated_target = validate_redirect_rule(
            site=site,
            source_path=src,
            target_url=target,
            rule_id=rule_id,
        )
        attrs["source_path"] = validated_src
        attrs["target_url"] = validated_target
        return attrs


class SEOAuditItemSerializer(serializers.Serializer[Any]):
    article_id = serializers.CharField()
    slug = serializers.CharField()
    field = serializers.CharField()
    severity = serializers.CharField()
    code = serializers.CharField()
    message = serializers.CharField()
    remediation = serializers.CharField()


class PublicSEOMetadataSerializer(serializers.Serializer[Any]):
    title = serializers.CharField()
    meta_description = serializers.CharField()
    canonical_url = serializers.CharField()
    robots = serializers.CharField()
    robots_index = serializers.BooleanField()
    robots_follow = serializers.BooleanField()
    open_graph = serializers.DictField()
    twitter = serializers.DictField()
    json_ld = serializers.DictField()
    json_ld_html = serializers.CharField()
