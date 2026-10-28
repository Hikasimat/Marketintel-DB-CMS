"""Tests for public content delivery API and origin allowlisting (CT-4, CT-6)."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.content.models import Article, ArticleStatus
from apps.sites.models import Site
from apps.tenancy.models import Workspace


@pytest.fixture
def public_setup(db: None) -> dict[str, object]:
    user = User.objects.create_user(email="author@example.com", password="Password123!")
    workspace = Workspace.objects.create(name="Public CMS WS", slug="public-cms-ws")

    active_site = Site.objects.create(
        workspace=workspace,
        name="Tech Chronicle",
        slug="tech-chronicle",
        allowed_origins=["https://tech.example.com", "https://preview.example.com"],
        is_active=True,
    )

    inactive_site = Site.objects.create(
        workspace=workspace,
        name="Old Site",
        slug="old-site",
        allowed_origins=["*"],
        is_active=False,
    )

    wildcard_site = Site.objects.create(
        workspace=workspace,
        name="Open Site",
        slug="open-site",
        allowed_origins=["*"],
        is_active=True,
    )

    # Published article on active site
    pub_art = Article.objects.create(
        site=active_site,
        author=user,
        title="Modern Python in 2026",
        slug="modern-python-2026",
        excerpt="Overview of Python features",
        body="Detailed body about Python 3.13 and beyond.",
        status=ArticleStatus.PUBLISHED,
    )

    # Draft article on active site
    draft_art = Article.objects.create(
        site=active_site,
        author=user,
        title="Draft Article",
        slug="draft-article",
        excerpt="Under development",
        body="Secret unpublished draft content",
        status=ArticleStatus.DRAFT,
    )

    # Archived article on active site
    archived_art = Article.objects.create(
        site=active_site,
        author=user,
        title="Archived Article",
        slug="archived-article",
        excerpt="Historical note",
        body="Old archived content",
        status=ArticleStatus.ARCHIVED,
    )

    return {
        "user": user,
        "workspace": workspace,
        "active_site": active_site,
        "inactive_site": inactive_site,
        "wildcard_site": wildcard_site,
        "published_article": pub_art,
        "draft_article": draft_art,
        "archived_article": archived_art,
    }


@pytest.mark.django_db
def test_public_articles_list_only_published(public_setup: dict[str, object]) -> None:
    client = APIClient()
    active_site = public_setup["active_site"]
    assert isinstance(active_site, Site)

    url = f"/api/v1/public/sites/{active_site.slug}/articles/"
    resp = client.get(url)
    assert resp.status_code == 200
    assert "Cache-Control" in resp.headers
    assert "public" in resp.headers["Cache-Control"]

    data = resp.json()
    assert data["count"] == 1
    assert data["results"][0]["slug"] == "modern-python-2026"
    assert data["results"][0]["title"] == "Modern Python in 2026"


@pytest.mark.django_db
def test_public_articles_detail_published_success(public_setup: dict[str, object]) -> None:
    client = APIClient()
    active_site = public_setup["active_site"]
    assert isinstance(active_site, Site)

    url = f"/api/v1/public/sites/{active_site.slug}/articles/modern-python-2026/"
    resp = client.get(url)
    assert resp.status_code == 200
    assert "ETag" in resp.headers
    assert "Cache-Control" in resp.headers

    data = resp.json()
    assert data["slug"] == "modern-python-2026"
    assert data["title"] == "Modern Python in 2026"
    assert data["body"] == "Detailed body about Python 3.13 and beyond."


@pytest.mark.django_db
def test_public_articles_detail_draft_or_archived_returns_404(
    public_setup: dict[str, object],
) -> None:
    client = APIClient()
    active_site = public_setup["active_site"]
    assert isinstance(active_site, Site)

    # Draft article must not be accessible via public endpoint
    draft_url = f"/api/v1/public/sites/{active_site.slug}/articles/draft-article/"
    resp = client.get(draft_url)
    assert resp.status_code == 404

    # Archived article must not be accessible via public endpoint
    archived_url = f"/api/v1/public/sites/{active_site.slug}/articles/archived-article/"
    resp = client.get(archived_url)
    assert resp.status_code == 404


@pytest.mark.django_db
def test_public_articles_inactive_or_nonexistent_site_returns_404(
    public_setup: dict[str, object],
) -> None:
    client = APIClient()
    inactive_site = public_setup["inactive_site"]
    assert isinstance(inactive_site, Site)

    resp = client.get(f"/api/v1/public/sites/{inactive_site.slug}/articles/")
    assert resp.status_code == 404

    resp = client.get("/api/v1/public/sites/totally-nonexistent-site/articles/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_public_origin_allowlist_enforcement(public_setup: dict[str, object]) -> None:
    """Test CT-6 Origin header enforcement."""
    client = APIClient()
    active_site = public_setup["active_site"]
    assert isinstance(active_site, Site)

    list_url = f"/api/v1/public/sites/{active_site.slug}/articles/"

    # 1. Allowed origin passes
    resp_ok = client.get(list_url, HTTP_ORIGIN="https://tech.example.com")
    assert resp_ok.status_code == 200

    # 2. Another allowed origin (with trailing slash stripped) passes
    resp_ok_slash = client.get(list_url, HTTP_ORIGIN="https://preview.example.com/")
    assert resp_ok_slash.status_code == 200

    # 3. Disallowed origin receives 403 Forbidden
    resp_forbidden = client.get(list_url, HTTP_ORIGIN="https://malicious.org")
    assert resp_forbidden.status_code == 403
    assert "not authorized" in resp_forbidden.json()["error"]["message"]

    # 4. Detail endpoint also rejects disallowed origin
    detail_url = f"/api/v1/public/sites/{active_site.slug}/articles/modern-python-2026/"
    resp_detail_forbidden = client.get(detail_url, HTTP_ORIGIN="https://malicious.org")
    assert resp_detail_forbidden.status_code == 403

    # 5. Wildcard site allows any origin
    wildcard_site = public_setup["wildcard_site"]
    assert isinstance(wildcard_site, Site)
    wildcard_url = f"/api/v1/public/sites/{wildcard_site.slug}/articles/"
    resp_wildcard = client.get(wildcard_url, HTTP_ORIGIN="https://any-origin.io")
    assert resp_wildcard.status_code == 200
