"""Models for Search Engine Integrations, IndexNow, and indexing submission logs (SEC-3, OPS-1)."""

from __future__ import annotations

import secrets
import uuid
from typing import ClassVar

from django.db import models

from apps.common.crypto import decrypt_secret, encrypt_secret
from apps.sites.models import Site


class SearchProvider(models.TextChoices):
    GOOGLE = "GOOGLE", "Google Search Console"
    BING = "BING", "Bing Webmaster Tools"
    INDEXNOW = "INDEXNOW", "IndexNow"


class ConnectionStatus(models.TextChoices):
    CONNECTED = "CONNECTED", "Connected"
    ERROR = "ERROR", "Error"
    DISCONNECTED = "DISCONNECTED", "Disconnected"


class SubmissionStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SUBMITTED = "SUBMITTED", "Submitted"
    FAILED = "FAILED", "Failed"


class SearchEngineConnection(models.Model):
    """Encrypted connection configuration to external search engine APIs (SEC-3)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="search_connections")
    provider = models.CharField(max_length=50, choices=SearchProvider.choices)
    encrypted_credentials = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=30, choices=ConnectionStatus.choices, default=ConnectionStatus.CONNECTED
    )
    last_synced_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    settings = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "integrations_search_connection"
        unique_together = ("site", "provider")
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["site", "provider"]),
        ]

    def __str__(self) -> str:
        return f"{self.site.name} -> {self.get_provider_display()} ({self.status})"

    def set_credentials(self, raw_credentials: str) -> None:
        """Encrypt credentials before persisting to database."""
        if not raw_credentials:
            self.encrypted_credentials = ""
        else:
            self.encrypted_credentials = encrypt_secret(raw_credentials)

    def get_credentials(self) -> str:
        """Decrypt credentials retrieved from database."""
        if not self.encrypted_credentials:
            return ""
        return decrypt_secret(self.encrypted_credentials)


class IndexNowKey(models.Model):
    """IndexNow host verification key hosted at https://<domain>/<key>.txt."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.OneToOneField(Site, on_delete=models.CASCADE, related_name="indexnow_key")
    key = models.CharField(max_length=64, unique=True)
    key_location = models.CharField(max_length=500, blank=True, default="")
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "integrations_indexnow_key"

    def __str__(self) -> str:
        return f"IndexNow Key for {self.site.name} ({self.key[:8]}...)"

    @classmethod
    def generate_for_site(cls, site: Site) -> IndexNowKey:
        """Generate a random 32-character hexadecimal IndexNow key."""
        hex_key = secrets.token_hex(16)  # 32 hex chars
        base_domain = site.domains.filter(is_verified=True, is_primary=True).first()
        hostname = base_domain.hostname if base_domain else f"{site.slug}.cms.local"
        location = f"https://{hostname}/{hex_key}.txt"

        obj, _ = cls.objects.update_or_create(
            site=site,
            defaults={"key": hex_key, "key_location": location},
        )
        return obj


class IndexSubmissionLog(models.Model):
    """Immutable audit trail and status of URL/sitemap submissions to search providers (OPS-1)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="submission_logs")
    provider = models.CharField(max_length=50, choices=SearchProvider.choices)
    urls = models.JSONField(default=list)
    idempotency_key = models.CharField(max_length=128, db_index=True)
    status = models.CharField(
        max_length=20, choices=SubmissionStatus.choices, default=SubmissionStatus.PENDING
    )
    response_code = models.IntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True, default="")
    retry_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "integrations_submission_log"
        ordering = ("-created_at",)
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["site", "provider", "created_at"]),
            models.Index(fields=["idempotency_key"]),
        ]

    def __str__(self) -> str:
        return f"{self.provider} submission for {self.site.slug} ({self.status})"
