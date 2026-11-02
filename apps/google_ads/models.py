"""Google Ads models for authorized connections, credentials, and campaign audit logging."""

from __future__ import annotations

import json
import uuid
from typing import Any, ClassVar

from django.db import models

from apps.accounts.models import User
from apps.common.crypto import decrypt_secret, encrypt_secret
from apps.tenancy.models import Workspace


class GoogleAdsConnection(models.Model):
    """Google Ads authorized OAuth connection scoped to a workspace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="google_ads_connections"
    )
    customer_id = models.CharField(
        max_length=50, blank=True, default="", help_text="Client customer ID (e.g. 123-456-7890)."
    )
    manager_customer_id = models.CharField(
        max_length=50, blank=True, default="", help_text="Manager account CID if accessing via MCC."
    )
    encrypted_credentials = models.TextField(
        blank=True, default="", help_text="Encrypted OAuth tokens JSON."
    )
    encrypted_developer_token = models.TextField(
        blank=True, default="", help_text="Encrypted developer token."
    )
    is_active = models.BooleanField(default=True)
    status = models.CharField(max_length=30, default="CONNECTED")
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "google_ads_connection"
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["workspace", "customer_id"]),
        ]

    def __str__(self) -> str:
        cid = self.customer_id or "Pending Selection"
        return f"Google Ads ({cid}) for Workspace {self.workspace.name}"

    def set_credentials(self, credentials_data: dict[str, Any]) -> None:
        """Encrypt and serialize OAuth credentials dictionary."""
        if not credentials_data:
            self.encrypted_credentials = ""
        else:
            raw_json = json.dumps(credentials_data)
            self.encrypted_credentials = encrypt_secret(raw_json)

    def get_credentials(self) -> dict[str, Any]:
        """Decrypt and deserialize OAuth credentials dictionary."""
        if not self.encrypted_credentials:
            return {}
        try:
            raw_json = decrypt_secret(self.encrypted_credentials)
            return json.loads(raw_json)
        except Exception:
            return {}

    def set_developer_token(self, token: str) -> None:
        if not token:
            self.encrypted_developer_token = ""
        else:
            self.encrypted_developer_token = encrypt_secret(token.strip())

    def get_developer_token(self) -> str:
        if not self.encrypted_developer_token:
            return ""
        try:
            return decrypt_secret(self.encrypted_developer_token)
        except Exception:
            return ""


class GoogleAdsCampaignAuditLog(models.Model):
    """Audit log for Google Ads campaign mutations (pause, resume, budget adjustments)."""

    class Action(models.TextChoices):
        CAMPAIGN_PAUSE = "CAMPAIGN_PAUSE", "Campaign Paused"
        CAMPAIGN_RESUME = "CAMPAIGN_RESUME", "Campaign Resumed"
        BUDGET_UPDATE = "BUDGET_UPDATE", "Budget Updated"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    connection = models.ForeignKey(
        GoogleAdsConnection, on_delete=models.CASCADE, related_name="audit_logs"
    )
    action = models.CharField(max_length=50, choices=Action.choices)
    campaign_id = models.CharField(max_length=50, db_index=True)
    campaign_name = models.CharField(max_length=255, blank=True, default="")
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "google_ads_campaign_audit_log"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.action} on Campaign {self.campaign_id} at {self.created_at.isoformat()}"
