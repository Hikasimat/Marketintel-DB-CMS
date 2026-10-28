"""Content lifecycle and revision versioning services."""

from __future__ import annotations

from typing import Any

from django.db import models, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import record_audit_event
from apps.content.models import Article, ArticleStatus, ArticleVersion


def create_article_version(article: Article, user: User | None = None) -> ArticleVersion:
    """Create an immutable revision snapshot for an Article."""
    max_ver = (
        ArticleVersion.objects.filter(article=article).aggregate(models.Max("version_number"))[
            "version_number__max"
        ]
        or 0
    )
    return ArticleVersion.objects.create(
        article=article,
        version_number=max_ver + 1,
        title=article.title,
        excerpt=article.excerpt,
        body=article.body,
        metadata=article.metadata,
        created_by=user,
    )


def publish_article(article: Article, user: User, request: Any = None) -> Article:
    """Transition article to PUBLISHED and record revision snapshot."""
    with transaction.atomic():
        article.status = ArticleStatus.PUBLISHED
        if not article.published_at:
            article.published_at = timezone.now()
        article.save()

        create_article_version(article, user=user)

        record_audit_event(
            action="article.published",
            request=request,
            workspace_id=article.site.workspace_id,
            actor=user,
            resource_type="article",
            resource_id=str(article.id),
            payload={"title": article.title, "slug": article.slug, "site": article.site.name},
        )
    return article


def restore_article_version(
    article: Article, version_number: int, user: User, request: Any = None
) -> Article:
    """Roll back article content to a previous version snapshot."""
    version = ArticleVersion.objects.get(article=article, version_number=version_number)

    with transaction.atomic():
        article.title = version.title
        article.excerpt = version.excerpt
        article.body = version.body
        article.metadata = version.metadata
        article.save()

        # Capture a new version documenting the rollback
        create_article_version(article, user=user)

        record_audit_event(
            action="article.version_restored",
            request=request,
            workspace_id=article.site.workspace_id,
            actor=user,
            resource_type="article",
            resource_id=str(article.id),
            payload={"restored_from_version": version_number},
        )
    return article
