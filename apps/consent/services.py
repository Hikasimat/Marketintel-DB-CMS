"""Consent domain services for recording, withdrawal, status verification, and GDPR compliance."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.services import record_audit_event
from apps.consent.models import (
    ConsentRecord,
    ConsentRecordStatus,
    ConsentType,
    PrivacyPolicyVersion,
    SiteConsentConfig,
)
from apps.consent.validators import (
    validate_categories_payload,
    validate_visitor_id,
)
from apps.sites.models import Site


def get_or_create_site_consent_config(site: Site) -> SiteConsentConfig:
    """Retrieve or create baseline SiteConsentConfig with defaults."""
    config, _ = SiteConsentConfig.objects.get_or_create(site=site)
    return config


def record_visitor_consent(
    site: Site,
    visitor_id: str,
    categories: dict[str, Any],
    policy_version_id: str | None = None,
    policy_version_str: str | None = None,
    consent_type: str = ConsentType.EXPLICIT_OPT_IN,
) -> ConsentRecord:
    """Record visitor consent choice with strict validation and category allowlist (CON-3)."""
    validate_visitor_id(visitor_id)
    config = get_or_create_site_consent_config(site)
    allowed_categories = config.get_all_categories()
    cleaned_categories = validate_categories_payload(categories, allowed_categories)

    # Resolve policy version
    policy_version: PrivacyPolicyVersion | None = None
    if policy_version_id:
        policy_version = site.privacy_policies.filter(id=policy_version_id).first()
        if not policy_version:
            raise ValidationError(
                {"policy_version": "Specified privacy policy version not found for this site."}
            )
    elif policy_version_str:
        policy_version = site.privacy_policies.filter(version=policy_version_str).first()
        if not policy_version:
            raise ValidationError(
                {
                    "policy_version": (
                        f"Policy version '{policy_version_str}' not found for this site."
                    )
                }
            )
    else:
        policy_version = config.active_policy_version
        if not policy_version:
            # Fallback to any active policy version for the site
            policy_version = site.privacy_policies.filter(is_active=True).first()

    # Determine status
    optional_cats = [k for k, v in cleaned_categories.items() if k != "necessary"]
    granted_optional = [k for k in optional_cats if cleaned_categories.get(k) is True]

    if optional_cats and len(granted_optional) == len(optional_cats):
        status_code = ConsentRecordStatus.GRANTED
    elif granted_optional:
        status_code = ConsentRecordStatus.PARTIALLY_GRANTED
    else:
        status_code = ConsentRecordStatus.DENIED

    now = timezone.now()
    expires_at = now + timedelta(days=config.retention_days)

    with transaction.atomic():
        # CON-4: Prior records remain in history, but new record captures current state
        record = ConsentRecord.objects.create(
            site=site,
            visitor_id=visitor_id,
            policy_version=policy_version,
            policy_version_string=policy_version.version if policy_version else "",
            categories=cleaned_categories,
            status=status_code,
            consent_type=consent_type,
            recorded_at=now,
            expires_at=expires_at,
        )

    return record


def withdraw_visitor_consent(site: Site, visitor_id: str) -> ConsentRecord:
    """Record visitor consent withdrawal, resetting all optional categories (CON-4).

    Preserves audit history by creating an immutable withdrawal record and marking
    prior decisions as withdrawn.
    """
    validate_visitor_id(visitor_id)
    config = get_or_create_site_consent_config(site)
    all_categories = config.get_all_categories()

    # All optional categories forced to False
    reset_categories: dict[str, bool] = {"necessary": True}
    for cat in all_categories:
        if cat != "necessary":
            reset_categories[cat] = False

    now = timezone.now()
    expires_at = now + timedelta(days=config.retention_days)

    with transaction.atomic():
        # Mark active prior records as withdrawn
        ConsentRecord.objects.filter(
            site=site,
            visitor_id=visitor_id,
            withdrawn_at__isnull=True,
        ).update(withdrawn_at=now, status=ConsentRecordStatus.WITHDRAWN)

        policy_version = config.active_policy_version

        record = ConsentRecord.objects.create(
            site=site,
            visitor_id=visitor_id,
            policy_version=policy_version,
            policy_version_string=policy_version.version if policy_version else "",
            categories=reset_categories,
            status=ConsentRecordStatus.WITHDRAWN,
            consent_type=ConsentType.WITHDRAWAL,
            recorded_at=now,
            withdrawn_at=now,
            expires_at=expires_at,
        )

    return record


def get_visitor_consent_status(site: Site, visitor_id: str) -> dict[str, Any]:
    """Retrieve the effective consent state for a visitor (CON-2, CON-4)."""
    validate_visitor_id(visitor_id)
    config = get_or_create_site_consent_config(site)

    latest_record = (
        ConsentRecord.objects.filter(site=site, visitor_id=visitor_id)
        .order_by("-recorded_at")
        .first()
    )

    active_policy = config.active_policy_version
    now = timezone.now()

    if not latest_record:
        # No consent given yet: default baseline
        return {
            "has_consent_record": False,
            "status": "NONE",
            "categories": config.get_default_category_states(),
            "policy_version": active_policy.version if active_policy else None,
            "requires_reconsent": True,
            "is_withdrawn": False,
        }

    is_expired = latest_record.expires_at < now
    is_withdrawn = (
        latest_record.status == ConsentRecordStatus.WITHDRAWN
        or latest_record.withdrawn_at is not None
    )

    # Check if policy version changed since consent was recorded (CON-4)
    policy_mismatch = False
    if active_policy and latest_record.policy_version_id != active_policy.id:
        policy_mismatch = True

    requires_reconsent = is_expired or is_withdrawn or policy_mismatch

    # If policy mismatch or withdrawn or expired, optional categories are suppressed
    effective_categories = dict(latest_record.categories)
    if requires_reconsent:
        for k in effective_categories:
            if k != "necessary":
                effective_categories[k] = False

    return {
        "has_consent_record": True,
        "record_id": str(latest_record.id),
        "status": latest_record.status,
        "categories": effective_categories,
        "recorded_at": latest_record.recorded_at.isoformat(),
        "expires_at": latest_record.expires_at.isoformat(),
        "policy_version": latest_record.policy_version_string,
        "requires_reconsent": requires_reconsent,
        "is_withdrawn": is_withdrawn,
    }


def purge_visitor_consent_history(site: Site, visitor_id: str, actor: Any = None) -> int:
    """Erase all consent history for a visitor under GDPR Art. 17 right to erasure (CON-6)."""
    validate_visitor_id(visitor_id)

    with transaction.atomic():
        deleted_count, _ = ConsentRecord.objects.filter(site=site, visitor_id=visitor_id).delete()

        record_audit_event(
            action="consent.visitor_records_purged",
            workspace_id=site.workspace_id,
            resource_type="ConsentRecord",
            resource_id=visitor_id[:16],  # Masked identifier for audit
            actor=actor,
            payload={"site_id": str(site.id), "records_deleted": deleted_count},
        )

    return deleted_count


def export_visitor_consent_history(site: Site, visitor_id: str) -> list[dict[str, Any]]:
    """Export complete visitor consent audit history under GDPR Art. 15/20 portability (CON-6)."""
    validate_visitor_id(visitor_id)

    records = ConsentRecord.objects.filter(site=site, visitor_id=visitor_id).order_by(
        "-recorded_at"
    )
    history: list[dict[str, Any]] = []
    for r in records:
        history.append(
            {
                "record_id": str(r.id),
                "status": r.status,
                "consent_type": r.consent_type,
                "categories": r.categories,
                "policy_version": r.policy_version_string,
                "recorded_at": r.recorded_at.isoformat(),
                "withdrawn_at": r.withdrawn_at.isoformat() if r.withdrawn_at else None,
                "expires_at": r.expires_at.isoformat(),
            }
        )

    return history


def get_consent_summary(site: Site) -> dict[str, Any]:
    """Calculate aggregated, anonymous consent statistics for workspace reporting."""
    records = ConsentRecord.objects.filter(site=site)
    total = records.count()
    if total == 0:
        return {
            "total_decisions": 0,
            "granted_count": 0,
            "partially_granted_count": 0,
            "denied_count": 0,
            "withdrawn_count": 0,
            "category_acceptance_rates": {},
        }

    granted = records.filter(status=ConsentRecordStatus.GRANTED).count()
    partially_granted = records.filter(status=ConsentRecordStatus.PARTIALLY_GRANTED).count()
    denied = records.filter(status=ConsentRecordStatus.DENIED).count()
    withdrawn = records.filter(status=ConsentRecordStatus.WITHDRAWN).count()

    config = get_or_create_site_consent_config(site)
    categories = list(config.get_all_categories().keys())

    acceptance_rates: dict[str, float] = {}
    for cat in categories:
        if cat == "necessary":
            acceptance_rates[cat] = 100.0
            continue
        accepted = (
            records.filter(categories__contains={cat: True})
            .exclude(status=ConsentRecordStatus.WITHDRAWN)
            .count()
        )
        rate = round((accepted / total) * 100, 1)
        acceptance_rates[cat] = rate

    return {
        "total_decisions": total,
        "granted_count": granted,
        "partially_granted_count": partially_granted,
        "denied_count": denied,
        "withdrawn_count": withdrawn,
        "category_acceptance_rates": acceptance_rates,
    }
