"""Content engine models for Articles, Revisions, and Media assets."""

from __future__ import annotations

import uuid
from typing import Any, ClassVar

from django.db import models
from django.utils.text import slugify

from apps.accounts.models import User
from apps.sites.models import Site
from apps.tenancy.models import Workspace


class ArticleStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    IN_REVIEW = "IN_REVIEW", "In Review"
    PUBLISHED = "PUBLISHED", "Published"
    ARCHIVED = "ARCHIVED", "Archived"


class ContentType(models.TextChoices):
    POST = "POST", "Blog Post"
    PAGE = "PAGE", "Static Page"
    CASE_STUDY = "CASE_STUDY", "Case Study"
    DOC = "DOC", "Documentation"


class Article(models.Model):
    """Core content document published to a Site."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="articles")
    author = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="authored_articles"
    )
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=200, db_index=True)
    excerpt = models.TextField(blank=True)
    body = models.TextField(blank=True)
    content_type = models.CharField(
        max_length=50, choices=ContentType.choices, default=ContentType.POST
    )
    status = models.CharField(
        max_length=20, choices=ArticleStatus.choices, default=ArticleStatus.DRAFT, db_index=True
    )
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "content_article"
        unique_together = ("site", "slug")
        ordering = ("-created_at",)
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["site", "slug"]),
            models.Index(fields=["site", "status", "published_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)


class ArticleVersion(models.Model):
    """Immutable snapshot revision tracking history and enabling version rollback."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    excerpt = models.TextField(blank=True)
    body = models.TextField(blank=True)
    metadata = models.JSONField(default=dict)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "content_article_version"
        unique_together = ("article", "version_number")
        ordering = ("-version_number",)
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["article", "version_number"]),
        ]

    def __str__(self) -> str:
        return f"{self.article.title} v{self.version_number}"


class MediaAsset(models.Model):
    """Metadata catalog for uploaded assets with file bounds and checksums."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="media_assets")
    site = models.ForeignKey(
        Site, on_delete=models.SET_NULL, null=True, blank=True, related_name="media_assets"
    )
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    file_size = models.PositiveIntegerField()
    storage_path = models.CharField(max_length=500)
    checksum_sha256 = models.CharField(max_length=64, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "content_media_asset"
        ordering = ("-created_at",)
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["workspace", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.filename} ({self.file_size} bytes)"
