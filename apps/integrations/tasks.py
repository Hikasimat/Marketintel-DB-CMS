"""Celery background tasks for search engine indexing submissions (OPS-1, SEC-3)."""

from __future__ import annotations

import hashlib
import json
import logging
import random
import uuid
from datetime import timedelta
from typing import Any

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.content.models import Article, ArticleStatus
from apps.integrations.adapters.bing import BingWebmasterAdapter
from apps.integrations.adapters.google import GoogleSearchConsoleAdapter
from apps.integrations.adapters.indexnow import IndexNowAdapter
from apps.integrations.models import (
    ConnectionStatus,
    IndexNowKey,
    IndexSubmissionLog,
    SearchEngineConnection,
    SearchProvider,
    SubmissionStatus,
)

logger = logging.getLogger(__name__)

# Max automatic retries for transient 429/5xx errors
MAX_RETRIES = 3


@shared_task(bind=True, max_retries=MAX_RETRIES)
def submit_indexing_job(self: Any, submission_log_id: str) -> dict[str, Any]:
    """Execute search engine submission with exponential backoff and jitter (OPS-1)."""
    try:
        log = IndexSubmissionLog.objects.select_related("site").get(id=submission_log_id)
    except IndexSubmissionLog.DoesNotExist:
        logger.warning("IndexSubmissionLog not found: %s", submission_log_id)
        return {"status": "NOT_FOUND", "log_id": submission_log_id}

    if log.status == SubmissionStatus.SUBMITTED:
        logger.info("Submission %s already completed, skipping.", submission_log_id)
        return {"status": "ALREADY_SUBMITTED", "log_id": submission_log_id}

    site = log.site
    primary_domain = site.domains.filter(is_verified=True, is_primary=True).first()
    hostname = primary_domain.hostname if primary_domain else f"{site.slug}.cms.local"
    site_url = f"https://{hostname}"

    result: dict[str, Any] = {}
    should_retry = False
    status_code: int | None = None

    try:
        if log.provider == SearchProvider.INDEXNOW:
            try:
                indexnow_key = site.indexnow_key
            except IndexNowKey.DoesNotExist:
                indexnow_key = IndexNowKey.generate_for_site(site)

            adapter = IndexNowAdapter(
                host=hostname,
                key=indexnow_key.key,
                key_location=indexnow_key.key_location,
            )
            result = adapter.submit_urls(log.urls)
            status_code = result.get("code", 200 if result.get("status") == "SUCCESS" else 400)

        elif log.provider == SearchProvider.BING:
            conn = SearchEngineConnection.objects.filter(
                site=site, provider=SearchProvider.BING
            ).first()
            if not conn:
                raise ValueError("Bing connection not configured for site.")
            api_key = conn.get_credentials()
            if not api_key:
                raise ValueError("Bing API key is empty.")

            bing_adapter = BingWebmasterAdapter(site_url=site_url, api_key=api_key)
            result = bing_adapter.submit_urls(log.urls)
            status_code = result.get("code", 200 if result.get("status") == "SUCCESS" else 400)

        elif log.provider == SearchProvider.GOOGLE:
            conn = SearchEngineConnection.objects.filter(
                site=site, provider=SearchProvider.GOOGLE
            ).first()
            if not conn:
                raise ValueError("Google Search Console connection not configured for site.")
            access_token = conn.get_credentials()
            if not access_token:
                raise ValueError("Google access token is empty.")

            google_adapter = GoogleSearchConsoleAdapter(
                site_url=site_url, access_token=access_token
            )
            # If sitemap URL is submitted, submit sitemap
            sitemap_urls = [u for u in log.urls if u.endswith(".xml")]
            if sitemap_urls:
                result = google_adapter.submit_sitemap(sitemap_urls[0])
            else:
                # Disallow standard URL indexing per Google guidelines
                result = {
                    "status": "SKIPPED",
                    "provider": "GOOGLE",
                    "reason": "Google Indexing API is restricted to JobPosting/Broadcast metadata.",
                }
            status_code = result.get("code", 200 if result.get("status") == "SUCCESS" else 400)

        else:
            raise ValueError(f"Unknown search provider: {log.provider}")

        # Evaluate response
        if result.get("status") in ("SUCCESS", "SKIPPED"):
            log.status = SubmissionStatus.SUBMITTED
            log.response_code = status_code or 200
            log.response_body = json.dumps(result)
            log.save(update_fields=["status", "response_code", "response_body", "updated_at"])

            # Update connection status
            SearchEngineConnection.objects.filter(site=site, provider=log.provider).update(
                status=ConnectionStatus.CONNECTED,
                last_synced_at=timezone.now(),
                error_message="",
            )
            return {"status": "SUCCESS", "log_id": submission_log_id, "result": result}

        # Check for transient errors that warrant retry
        if status_code in (429, 500, 502, 503, 504):
            should_retry = True

    except Exception as exc:
        logger.exception("Error executing indexing job %s: %s", submission_log_id, exc)
        result = {"status": "ERROR", "error": str(exc)}
        should_retry = True

    if should_retry and self.request.retries < MAX_RETRIES:
        log.retry_count = self.request.retries + 1
        log.response_code = status_code
        log.response_body = json.dumps(result)
        log.save(update_fields=["retry_count", "response_code", "response_body", "updated_at"])

        # Exponential backoff with jitter: 2^retries + uniform(0.5, 2.0)
        countdown = (2**self.request.retries) + random.uniform(0.5, 2.0)  # nosec B311  # noqa: S311
        raise self.retry(countdown=countdown)

    # Permanent failure or max retries exceeded
    log.status = SubmissionStatus.FAILED
    log.response_code = status_code or 500
    log.response_body = json.dumps(result)
    log.save(update_fields=["status", "response_code", "response_body", "updated_at"])

    SearchEngineConnection.objects.filter(site=site, provider=log.provider).update(
        status=ConnectionStatus.ERROR,
        error_message=str(result.get("error", "Indexing submission failed.")),
    )
    return {"status": "FAILED", "log_id": submission_log_id, "result": result}


def notify_search_engines_for_article(article_id: uuid.UUID | str) -> list[str]:
    """Publish notification hook: enqueues background indexing submissions (OPS-1)."""
    try:
        article = (
            Article.objects.select_related("site")
            .prefetch_related("site__domains", "site__search_connections")
            .get(id=article_id)
        )
    except Article.DoesNotExist:
        return []

    if article.status != ArticleStatus.PUBLISHED:
        return []

    site = article.site
    primary_domain = site.domains.filter(is_verified=True, is_primary=True).first()
    hostname = primary_domain.hostname if primary_domain else f"{site.slug}.cms.local"
    article_url = f"https://{hostname}/{article.slug}"

    # Determine configured providers
    providers: list[str] = []
    # If IndexNow key exists, include IndexNow
    if hasattr(site, "indexnow_key") or site.domains.filter(is_verified=True).exists():
        providers.append(SearchProvider.INDEXNOW)

    active_connections = site.search_connections.filter(status=ConnectionStatus.CONNECTED)
    for conn in active_connections:
        if conn.provider not in providers and conn.provider != SearchProvider.INDEXNOW:
            providers.append(conn.provider)

    enqueued_log_ids: list[str] = []
    now = timezone.now()
    # 1 hour deduplication window
    dedup_cutoff = now - timedelta(hours=1)

    for provider in providers:
        raw_key = f"{site.id}:{provider}:{article.id}:{article.updated_at.strftime('%Y%m%d%H')}"
        idempotency_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

        with transaction.atomic():
            # Check deduplication window
            recent = IndexSubmissionLog.objects.filter(
                idempotency_key=idempotency_key,
                created_at__gte=dedup_cutoff,
            ).first()

            if recent:
                logger.info(
                    "Skipping duplicate submission for %s on %s within dedup window.",
                    article.slug,
                    provider,
                )
                continue

            log = IndexSubmissionLog.objects.create(
                site=site,
                provider=provider,
                urls=[article_url],
                idempotency_key=idempotency_key,
                status=SubmissionStatus.PENDING,
            )
            enqueued_log_ids.append(str(log.id))
            submit_indexing_job.delay(str(log.id))

    return enqueued_log_ids
