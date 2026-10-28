"""Consent management models for cookie categories, policy versions, and visitor records."""

from __future__ import annotations

import uuid
from typing import Any, ClassVar

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.sites.models import Site

DEFAULT_CATEGORIES: dict[str, dict[str, Any]] = {
    "necessary": {
        "title": "Strictly Necessary",
        "description": (
            "Essential cookies required for security, network management, and accessibility. "
            "Cannot be disabled."
        ),
        "required": True,
        "default_state": True,
    },
    "analytics": {
        "title": "Analytics & Performance",
        "description": (
            "Helps us improve website experience by collecting and reporting aggregated "
            "information anonymously."
        ),
        "required": False,
        "default_state": False,
    },
    "marketing": {
        "title": "Marketing & Advertising",
        "description": "Used to deliver tailored advertisements and evaluate marketing campaigns.",
        "required": False,
        "default_state": False,
    },
    "preferences": {
        "title": "Functional & Preferences",
        "description": (
            "Enables the website to remember choices such as language, region, or theme."
        ),
        "required": False,
        "default_state": False,
    },
}


class JurisdictionMode(models.TextChoices):
    GDPR = "GDPR", "GDPR (Strict Opt-in)"
    CCPA_CPRA = "CCPA_CPRA", "CCPA/CPRA (Opt-out)"
    GLOBAL_OPT_IN = "GLOBAL_OPT_IN", "Global Opt-in"
    GLOBAL_OPT_OUT = "GLOBAL_OPT_OUT", "Global Opt-out"


class GCMState(models.TextChoices):
    GRANTED = "granted", "Granted"
    DENIED = "denied", "Denied"


class ConsentRecordStatus(models.TextChoices):
    GRANTED = "GRANTED", "Granted"
    PARTIALLY_GRANTED = "PARTIALLY_GRANTED", "Partially Granted"
    DENIED = "DENIED", "Denied"
    WITHDRAWN = "WITHDRAWN", "Withdrawn"


class ConsentType(models.TextChoices):
    EXPLICIT_OPT_IN = "EXPLICIT_OPT_IN", "Explicit Opt-in"
    OPT_OUT = "OPT_OUT", "Opt-out"
    IMPLICIT_NECESSARY_ONLY = "IMPLICIT_NECESSARY_ONLY", "Implicit Necessary Only"
    WITHDRAWAL = "WITHDRAWAL", "Withdrawal"


class SiteConsentConfig(models.Model):
    """Per-site cookie consent and privacy configuration (CON-1, CON-2)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.OneToOneField(Site, on_delete=models.CASCADE, related_name="consent_config")
    is_enabled = models.BooleanField(
        default=True,
        help_text="Master switch for consent management on this site.",
    )
    jurisdiction_mode = models.CharField(
        max_length=30,
        choices=JurisdictionMode.choices,
        default=JurisdictionMode.GDPR,
        help_text="Jurisdiction compliance mode determining default gating rules.",
    )
    retention_days = models.PositiveIntegerField(
        default=365,
        help_text="Consent record retention duration in days (30 to 1095 days).",
    )
    cookie_domain = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Optional root cookie domain for subdomains.",
    )
    active_policy_version = models.ForeignKey(
        "consent.PrivacyPolicyVersion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Currently active privacy policy version for visitor consent.",
    )
    categories = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Extended custom categories dictionary. Adding new optional categories "
            "never enables them silently (CON-5)."
        ),
    )

    # Google Consent Mode v2 default directives (CON-2)
    gcm_enabled = models.BooleanField(
        default=False,
        help_text="Support Google Consent Mode v2 signal dispatch contract.",
    )
    gcm_default_analytics_storage = models.CharField(
        max_length=10,
        choices=GCMState.choices,
        default=GCMState.DENIED,
    )
    gcm_default_ad_storage = models.CharField(
        max_length=10,
        choices=GCMState.choices,
        default=GCMState.DENIED,
    )
    gcm_default_ad_user_data = models.CharField(
        max_length=10,
        choices=GCMState.choices,
        default=GCMState.DENIED,
    )
    gcm_default_ad_personalization = models.CharField(
        max_length=10,
        choices=GCMState.choices,
        default=GCMState.DENIED,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "consent_site_config"

    def __str__(self) -> str:
        return f"Consent Config for {self.site.name}"

    def clean(self) -> None:
        if self.retention_days < 30 or self.retention_days > 1095:
            raise ValidationError({"retention_days": "retention_days must be between 30 and 1095."})

        # Ensure custom categories enforce CON-5
        if self.categories:
            if not isinstance(self.categories, dict):
                raise ValidationError({"categories": "categories must be a JSON dictionary."})
            for key, val in self.categories.items():
                if not isinstance(val, dict):
                    raise ValidationError(
                        {"categories": f"Category '{key}' configuration must be a dictionary."}
                    )
                if key == "necessary":
                    raise ValidationError(
                        {"categories": "Cannot redefine the 'necessary' category."}
                    )
                # Enforce CON-5: New optional categories can never be silently enabled by default
                val["required"] = False
                val["default_state"] = False

    def get_all_categories(self) -> dict[str, dict[str, Any]]:
        """Returns default categories merged with verified custom categories (CON-1, CON-5)."""
        combined = dict(DEFAULT_CATEGORIES)
        if self.categories and isinstance(self.categories, dict):
            for key, val in self.categories.items():
                if key != "necessary" and isinstance(val, dict):
                    combined[key] = {
                        "title": val.get("title", key.replace("_", " ").title()),
                        "description": val.get("description", ""),
                        "required": False,  # Never required for custom categories
                        "default_state": False,  # CON-5: Always False by default
                    }
        return combined

    def get_default_category_states(self) -> dict[str, bool]:
        """Returns baseline category states prior to visitor consent."""
        cats = self.get_all_categories()
        return {k: info["default_state"] for k, info in cats.items()}

    def get_gcm_defaults(self) -> dict[str, str]:
        """Returns Google Consent Mode v2 default signal mapping (CON-2)."""
        if not self.gcm_enabled:
            return {}
        return {
            "analytics_storage": self.gcm_default_analytics_storage,
            "ad_storage": self.gcm_default_ad_storage,
            "ad_user_data": self.gcm_default_ad_user_data,
            "ad_personalization": self.gcm_default_ad_personalization,
        }


class PrivacyPolicyVersion(models.Model):
    """Versioned privacy policy document requiring visitor consent acknowledgment (CON-1, CON-4)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="privacy_policies")
    version = models.CharField(
        max_length=50, help_text="Version identifier (e.g. '1.0', '2026.1')."
    )
    title = models.CharField(max_length=255, help_text="Policy version title.")
    summary = models.TextField(blank=True, default="", help_text="Summary of major changes.")
    body = models.TextField(
        blank=True, default="", help_text="Full markdown or text policy content."
    )
    is_active = models.BooleanField(
        default=False,
        help_text="Whether this version is the currently enforced policy version for the site.",
    )
    effective_date = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "consent_privacy_policy_version"
        ordering: ClassVar[list[str]] = ["-effective_date", "-created_at"]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["site", "version"],
                name="unique_site_privacy_policy_version",
            )
        ]

    def __str__(self) -> str:
        return f"{self.site.name} Policy v{self.version}"

    def activate(self) -> None:
        """Atomically activate this version and deactivate all sibling versions."""
        with transaction.atomic():
            # Deactivate other versions
            PrivacyPolicyVersion.objects.filter(site=self.site, is_active=True).exclude(
                pk=self.pk
            ).update(is_active=False)
            self.is_active = True
            self.save(update_fields=["is_active", "updated_at"])

            # Link on SiteConsentConfig
            config, _ = SiteConsentConfig.objects.get_or_create(site=self.site)
            config.active_policy_version = self
            config.save(update_fields=["active_policy_version", "updated_at"])


class ConsentRecord(models.Model):
    """Immutable audit record of visitor consent choice and category preferences (CON-3, CON-4)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="consent_records")
    visitor_id = models.CharField(
        max_length=128,
        db_index=True,
        help_text="Opaque pseudonymous client identifier. Zero raw IP stored (CON-3, ANA-5).",
    )
    policy_version = models.ForeignKey(
        PrivacyPolicyVersion,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="consent_records",
    )
    policy_version_string = models.CharField(max_length=50, blank=True, default="")
    categories = models.JSONField(
        default=dict,
        help_text="Category states dictionary {'necessary': True, 'analytics': False, ...}.",
    )
    status = models.CharField(
        max_length=20,
        choices=ConsentRecordStatus.choices,
        default=ConsentRecordStatus.GRANTED,
        db_index=True,
    )
    consent_type = models.CharField(
        max_length=30,
        choices=ConsentType.choices,
        default=ConsentType.EXPLICIT_OPT_IN,
    )
    recorded_at = models.DateTimeField(default=timezone.now, db_index=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "consent_record"
        ordering: ClassVar[list[str]] = ["-recorded_at"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["site", "visitor_id", "-recorded_at"]),
            models.Index(fields=["site", "expires_at"]),
        ]

    def __str__(self) -> str:
        return f"Consent for {self.visitor_id[:8]}... on {self.site.name} ({self.status})"

    def withdraw(self) -> None:
        """Mark this consent decision as withdrawn, resetting all optional categories (CON-4)."""
        now = timezone.now()
        self.withdrawn_at = now
        self.status = ConsentRecordStatus.WITHDRAWN
        self.consent_type = ConsentType.WITHDRAWAL

        # Disable all optional categories
        new_categories: dict[str, bool] = {"necessary": True}
        for k in self.categories:
            if k != "necessary":
                new_categories[k] = False
        self.categories = new_categories
        self.save(update_fields=["withdrawn_at", "status", "consent_type", "categories"])
