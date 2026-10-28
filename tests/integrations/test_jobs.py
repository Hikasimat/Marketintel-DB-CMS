"""Tests for background publishing jobs, Celery indexing tasks, and rate-limit backoff (OPS-1)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from celery.exceptions import Retry

from apps.accounts.models import User
from apps.content.models import Article, ArticleStatus
from apps.content.services import publish_article
from apps.integrations.models import (
    ConnectionStatus,
    IndexNowKey,
    IndexSubmissionLog,
    SearchEngineConnection,
    SearchProvider,
    SubmissionStatus,
)
from apps.integrations.tasks import (
    MAX_RETRIES,
    notify_search_engines_for_article,
    submit_indexing_job,
)
from apps.sites.models import Domain, Site
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole


@pytest.fixture
def publishing_setup(db: None) -> dict[str, object]:
    user = User.objects.create_user(email="publisher@test.com", password="SecurePassword123!")
    workspace = Workspace.objects.create(name="Publishing Org", slug="pub-org")
    WorkspaceMembership.objects.create(workspace=workspace, user=user, role=WorkspaceRole.ADMIN)
    site = Site.objects.create(workspace=workspace, name="News Site", slug="news-site")
    domain = Domain.objects.create(
        site=site, hostname="news.example.com", is_verified=True, is_primary=True
    )

    # Configure Bing connection
    bing_conn = SearchEngineConnection.objects.create(
        site=site,
        provider=SearchProvider.BING,
        status=ConnectionStatus.CONNECTED,
    )
    bing_conn.set_credentials("bing-test-api-key")  # nosec B106
    bing_conn.save()

    # Configure IndexNow key
    indexnow_key = IndexNowKey.generate_for_site(site)

    article = Article.objects.create(
        site=site,
        title="Breaking News",
        slug="breaking-news",
        body="Important content...",
        status=ArticleStatus.DRAFT,
    )

    return {
        "user": user,
        "workspace": workspace,
        "site": site,
        "domain": domain,
        "bing_conn": bing_conn,
        "indexnow_key": indexnow_key,
        "article": article,
    }


@pytest.mark.django_db
def test_submit_indexing_job_indexnow_success(publishing_setup: dict[str, object]) -> None:
    site = publishing_setup["site"]
    assert isinstance(site, Site)

    log = IndexSubmissionLog.objects.create(
        site=site,
        provider=SearchProvider.INDEXNOW,
        urls=["https://news.example.com/breaking-news"],
        idempotency_key="idemp-indexnow-1",
    )

    with patch("apps.integrations.tasks.IndexNowAdapter.submit_urls") as mock_submit:
        mock_submit.return_value = {"status": "SUCCESS", "code": 200, "submitted_count": 1}
        res = submit_indexing_job(str(log.id))

    assert res["status"] == "SUCCESS"
    log.refresh_from_db()
    assert log.status == SubmissionStatus.SUBMITTED
    assert log.response_code == 200


@pytest.mark.django_db
def test_submit_indexing_job_already_submitted_skipped(publishing_setup: dict[str, object]) -> None:
    site = publishing_setup["site"]
    assert isinstance(site, Site)

    log = IndexSubmissionLog.objects.create(
        site=site,
        provider=SearchProvider.INDEXNOW,
        urls=["https://news.example.com/breaking-news"],
        idempotency_key="idemp-indexnow-2",
        status=SubmissionStatus.SUBMITTED,
    )
    res = submit_indexing_job(str(log.id))
    assert res["status"] == "ALREADY_SUBMITTED"


@pytest.mark.django_db
def test_submit_indexing_job_not_found() -> None:
    res = submit_indexing_job("00000000-0000-0000-0000-000000000000")
    assert res["status"] == "NOT_FOUND"


@pytest.mark.django_db
def test_submit_indexing_job_bing_success(publishing_setup: dict[str, object]) -> None:
    site = publishing_setup["site"]
    assert isinstance(site, Site)

    log = IndexSubmissionLog.objects.create(
        site=site,
        provider=SearchProvider.BING,
        urls=["https://news.example.com/breaking-news"],
        idempotency_key="idemp-bing-1",
    )

    with patch("apps.integrations.tasks.BingWebmasterAdapter.submit_urls") as mock_submit:
        mock_submit.return_value = {"status": "SUCCESS", "submitted_count": 1}
        res = submit_indexing_job(str(log.id))

    assert res["status"] == "SUCCESS"
    log.refresh_from_db()
    assert log.status == SubmissionStatus.SUBMITTED


@pytest.mark.django_db
def test_submit_indexing_job_google_sitemap_success(publishing_setup: dict[str, object]) -> None:
    site = publishing_setup["site"]
    assert isinstance(site, Site)

    google_conn = SearchEngineConnection.objects.create(
        site=site,
        provider=SearchProvider.GOOGLE,
        status=ConnectionStatus.CONNECTED,
    )
    google_conn.set_credentials("google-access-token")  # nosec B106
    google_conn.save()

    log = IndexSubmissionLog.objects.create(
        site=site,
        provider=SearchProvider.GOOGLE,
        urls=["https://news.example.com/sitemap.xml"],
        idempotency_key="idemp-google-1",
    )

    with patch("apps.integrations.tasks.GoogleSearchConsoleAdapter.submit_sitemap") as mock_submit:
        mock_submit.return_value = {"status": "SUCCESS", "provider": "GOOGLE"}
        res = submit_indexing_job(str(log.id))

    assert res["status"] == "SUCCESS"
    log.refresh_from_db()
    assert log.status == SubmissionStatus.SUBMITTED


@pytest.mark.django_db
def test_submit_indexing_job_retry_on_rate_limit_or_server_error(
    publishing_setup: dict[str, object],
) -> None:
    site = publishing_setup["site"]
    assert isinstance(site, Site)

    log = IndexSubmissionLog.objects.create(
        site=site,
        provider=SearchProvider.BING,
        urls=["https://news.example.com/breaking-news"],
        idempotency_key="idemp-bing-retry",
    )

    with patch("apps.integrations.tasks.BingWebmasterAdapter.submit_urls") as mock_submit:
        mock_submit.return_value = {"status": "ERROR", "code": 429, "error": "Rate limited"}

        # Simulate Celery task instance with retries < MAX_RETRIES
        task_mock = MagicMock()
        task_mock.request.retries = 0
        task_mock.retry.side_effect = Retry("Simulated task retry")

        with pytest.raises(Retry):
            submit_indexing_job.run.__func__(task_mock, str(log.id))

        log.refresh_from_db()
        assert log.retry_count == 1
        assert task_mock.retry.called
        call_kwargs = task_mock.retry.call_args[1]
        assert "countdown" in call_kwargs


@pytest.mark.django_db
def test_submit_indexing_job_max_retries_exceeded_marks_failed(
    publishing_setup: dict[str, object],
) -> None:
    site = publishing_setup["site"]
    assert isinstance(site, Site)

    log = IndexSubmissionLog.objects.create(
        site=site,
        provider=SearchProvider.BING,
        urls=["https://news.example.com/breaking-news"],
        idempotency_key="idemp-bing-fail",
    )

    with patch("apps.integrations.tasks.BingWebmasterAdapter.submit_urls") as mock_submit:
        mock_submit.return_value = {"status": "ERROR", "code": 500, "error": "Fatal Error"}

        task_mock = MagicMock()
        task_mock.request.retries = MAX_RETRIES

        res = submit_indexing_job.run.__func__(task_mock, str(log.id))

        assert res["status"] == "FAILED"
        log.refresh_from_db()
        assert log.status == SubmissionStatus.FAILED
        assert log.response_code == 500


@pytest.mark.django_db
def test_notify_search_engines_for_article_enqueues_and_deduplicates(
    publishing_setup: dict[str, object],
) -> None:
    article = publishing_setup["article"]
    user = publishing_setup["user"]
    assert isinstance(article, Article)
    assert isinstance(user, User)

    # 1. Unpublished article does not notify
    enqueued = notify_search_engines_for_article(article.id)
    assert enqueued == []

    # 2. Publish article
    with patch("apps.integrations.tasks.submit_indexing_job.delay") as mock_delay:
        publish_article(article, user=user)
        # Manually trigger notify
        enqueued = notify_search_engines_for_article(article.id)
        assert len(enqueued) > 0
        assert mock_delay.called

        # 3. Duplicate notification within 1-hour deduplication window is skipped
        duplicate_enqueued = notify_search_engines_for_article(article.id)
        assert duplicate_enqueued == []
