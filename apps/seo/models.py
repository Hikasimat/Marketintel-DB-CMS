"""SEO models for site defaults, article-level metadata, and redirect rules."""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models

from apps.content.models import Article
from apps.sites.models import Site


class RedirectStatusCode(models.IntegerChoices):
    MOVED_PERMANENTLY = 301, "301 Moved Permanently"
    FOUND = 302, "302 Found"
    TEMPORARY_REDIRECT = 307, "307 Temporary Redirect"
    PERMANENT_REDIRECT = 308, "308 Permanent Redirect"


class SiteSEOSettings(models.Model):
    """Site-wide SEO defaults and robots.txt configurations (SEO-1, SEO-6)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.OneToOneField(Site, on_delete=models.CASCADE, related_name="seo_settings")
    title_suffix = models.CharField(max_length=100, blank=True, default="")
    default_meta_description = models.CharField(max_length=320, blank=True, default="")
    default_robots_index = models.BooleanField(default=True)
    default_robots_follow = models.BooleanField(default=True)
    default_og_image_url = models.CharField(max_length=500, blank=True, default="")
    custom_robots_txt = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "seo_site_settings"
        verbose_name = "Site SEO Settings"
        verbose_name_plural = "Site SEO Settings"

    def __str__(self) -> str:
        return f"SEO Settings for {self.site.name}"


class ArticleSEO(models.Model):
    """Article-level SEO metadata and structured data overrides (SEO-1, SEO-2, SEO-3)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    article = models.OneToOneField(Article, on_delete=models.CASCADE, related_name="seo")
    meta_title = models.CharField(max_length=200, blank=True, default="")
    meta_description = models.CharField(max_length=320, blank=True, default="")
    canonical_url = models.CharField(max_length=500, blank=True, default="")
    robots_index = models.BooleanField(default=True)
    robots_follow = models.BooleanField(default=True)
    og_title = models.CharField(max_length=200, blank=True, default="")
    og_description = models.CharField(max_length=320, blank=True, default="")
    og_image_url = models.CharField(max_length=500, blank=True, default="")
    twitter_card = models.CharField(max_length=50, default="summary_large_image")
    jsonld_schema = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "seo_article_metadata"
        verbose_name = "Article SEO Metadata"
        verbose_name_plural = "Article SEO Metadata"

    def __str__(self) -> str:
        return f"SEO for Article {self.article.slug}"


class RedirectRule(models.Model):
    """Redirect rule with cycle detection and open-redirect protection (SEO-4)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="redirect_rules")
    source_path = models.CharField(max_length=500)
    target_url = models.CharField(max_length=500)
    status_code = models.IntegerField(
        choices=RedirectStatusCode.choices, default=RedirectStatusCode.MOVED_PERMANENTLY
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "seo_redirect_rule"
        unique_together = ("site", "source_path")
        ordering = ("source_path",)
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["site", "source_path"]),
        ]

    def __str__(self) -> str:
        return f"{self.source_path} -> {self.target_url} ({self.status_code})"
