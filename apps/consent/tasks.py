"""Celery background tasks for consent record retention and automated pruning (CON-6)."""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task
from django.utils import timezone

from apps.consent.models import ConsentRecord

logger = logging.getLogger(__name__)


@shared_task(name="apps.consent.tasks.cleanup_expired_consent_records")
def cleanup_expired_consent_records() -> dict[str, Any]:
    """Delete expired consent records exceeding retention limits (CON-6)."""
    now = timezone.now()
    try:
        deleted_count, _ = ConsentRecord.objects.filter(expires_at__lt=now).delete()
        logger.info(
            "Pruned expired consent records",
            extra={"deleted_count": deleted_count, "operation": "cleanup_expired_consent_records"},
        )
        return {"status": "SUCCESS", "deleted_count": deleted_count}
    except Exception as exc:
        logger.error(
            "Failed to cleanup expired consent records",
            extra={"error": str(exc), "operation": "cleanup_expired_consent_records"},
        )
        return {"status": "FAILED", "error": str(exc)}
