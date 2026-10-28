"""Site and custom domain models for multi-tenant web publishing."""

from __future__ import annotations

import uuid
from typing import Any, ClassVar

from django.db import models
from django.utils.text import slugify

from apps.sites.validators import validate_hostname
from apps.tenancy.models import Workspace


class Site(models.Model):
    """A web property / publication owned by a Workspace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="sites")
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=100, db_index=True)
    default_locale = models.CharField(max_length=20, default="en-US")
    theme_config = models.JSONField(default=dict)
    settings = models.JSONField(default=dict)
    allowed_origins = models.JSONField(default=list)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sites_site"
        unique_together = ("workspace", "slug")
        ordering = ("name",)
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["workspace", "slug"]),
            models.Index(fields=["slug", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.slug})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Domain(models.Model):
    """Custom domain registered and verified for a Site."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="domains")
    hostname = models.CharField(max_length=253, unique=True, db_index=True)
    is_primary = models.BooleanField(default=False)
    verification_token = models.UUIDField(default=uuid.uuid4)
    is_verified = models.BooleanField(default=False, db_index=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    ssl_status = models.CharField(max_length=20, default="PENDING")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sites_domain"
        ordering = ("-is_primary", "hostname")
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["site", "is_primary"]),
        ]

    def __str__(self) -> str:
        verified = "verified" if self.is_verified else "unverified"
        return f"{self.hostname} ({verified})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.hostname = validate_hostname(self.hostname)
        super().save(*args, **kwargs)

    def clean(self) -> None:
        self.hostname = validate_hostname(self.hostname)
        super().clean()
