"""Models for GitHub App installations, repository connections, and webhook replay protection."""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.db import models

from apps.sites.models import Site
from apps.tenancy.models import Workspace


class DetectedFramework(models.TextChoices):
    NEXT_JS = "NEXT_JS", "Next.js"
    VITE_REACT = "VITE_REACT", "Vite (React)"
    ASTRO = "ASTRO", "Astro"
    NUXT = "NUXT", "Nuxt"
    REMIX = "REMIX", "Remix"
    UNSUPPORTED = "UNSUPPORTED", "Unsupported Framework"


class IntegrationStatus(models.TextChoices):
    CONNECTED = "CONNECTED", "Connected"
    ANALYZED = "ANALYZED", "Framework Analyzed"
    PR_OPENED = "PR_OPENED", "Pull Request Opened"
    FAILED = "FAILED", "Integration Failed"
    DISCONNECTED = "DISCONNECTED", "Disconnected"


class GitHubAppInstallation(models.Model):
    """Authorized GitHub App installation for a workspace (GH-1)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="github_installations"
    )
    installation_id = models.BigIntegerField(unique=True, db_index=True)
    account_login = models.CharField(max_length=255)
    account_type = models.CharField(max_length=50, default="User")
    repository_selection = models.CharField(max_length=20, default="selected")
    permissions = models.JSONField(
        default=dict,
        blank=True,
        help_text="Snapshot of granted GitHub App permissions (contents, pull_requests, metadata).",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Active state of this installation; toggled False upon uninstall or suspension.",
    )
    suspended_at = models.DateTimeField(null=True, blank=True)
    installed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "github_app_installation"
        ordering: ClassVar[list[str]] = ["-installed_at"]

    def __str__(self) -> str:
        return f"GitHub App Installation {self.installation_id} ({self.account_login})"


class SiteGitHubRepoConnection(models.Model):
    """Customer-selected repository connection for a site (GH-2, GH-4)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.OneToOneField(Site, on_delete=models.CASCADE, related_name="github_connection")
    installation = models.ForeignKey(
        GitHubAppInstallation, on_delete=models.CASCADE, related_name="connections"
    )
    repo_full_name = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Repository slug (owner/repo).",
    )
    default_branch = models.CharField(max_length=100, default="main")
    selected_branch = models.CharField(max_length=100, default="main")
    detected_framework = models.CharField(
        max_length=30,
        choices=DetectedFramework.choices,
        default=DetectedFramework.UNSUPPORTED,
    )
    framework_manifest = models.JSONField(
        default=dict,
        blank=True,
        help_text="Extracted dependency metadata parsed strictly as untrusted data (GH-3).",
    )
    integration_status = models.CharField(
        max_length=30,
        choices=IntegrationStatus.choices,
        default=IntegrationStatus.CONNECTED,
    )
    last_pr_url = models.URLField(max_length=500, blank=True, default="")
    last_pr_number = models.PositiveIntegerField(null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "github_repo_connection"
        ordering: ClassVar[list[str]] = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.site.name} -> {self.repo_full_name} ({self.selected_branch})"


class GitHubWebhookDelivery(models.Model):
    """Audit and replay defense record for inbound GitHub webhooks (GH-6)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    delivery_id = models.CharField(max_length=128, unique=True, db_index=True)
    event_type = models.CharField(max_length=64)
    processed_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=30, default="PROCESSED")

    class Meta:
        db_table = "github_webhook_delivery"
        ordering: ClassVar[list[str]] = ["-processed_at"]

    def __str__(self) -> str:
        return f"Webhook Delivery {self.delivery_id} ({self.event_type})"
