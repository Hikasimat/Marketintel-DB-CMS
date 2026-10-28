"""Tests for XML sitemap generation and robots.txt endpoint contracts (SEO-5, SEO-6)."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.content.models import Article, ArticleStatus
from apps.seo.models import ArticleSEO, SiteSEOSettings
from apps.sites.models import Domain, Site
from apps.tenancy.models import Workspace


@pytest.fixture
def sitemap_setup(db: None) -> dict[str, object]:
    user = User.objects.create_user(email="publisher@example.com", password="SecurePassword123!")
    workspace = Workspace.objects.create(name="Sitemap Org", slug="sitemap-org")

    site = Site.objects.create(
        workspace=workspace,
        name="Portal News",
        slug="portal-news",
        is_active=True,
    )
    Domain.objects.create(
        site=site,
        hostname="portal.example.com",
        is_verified=True,
        is_primary=True,
    )

    inactive_site = Site.objects.create(
        workspace=workspace,
        name="Inactive Site",
        slug="inactive-site",
        is_active=False,
    )

    # 1. Published indexable article
    art1 = Article.objects.create(
        site=site,
        author=user,
        title="Public Tech Report",
        slug="public-tech-report",
        body="Article content",
        status=ArticleStatus.PUBLISHED,
    )
    ArticleSEO.objects.create(article=art1, robots_index=True)

    # 2. Published noindex article
    art2 = Article.objects.create(
        site=site,
        author=user,
        title="Private Thank You Page",
        slug="private-thank-you-page",
        body="Secret page",
        status=ArticleStatus.PUBLISHED,
    )
    ArticleSEO.objects.create(article=art2, robots_index=False)

    # 3. Draft article
    Article.objects.create(
        site=site,
        author=user,
        title="Draft Article Post",
        slug="draft-article-post",
        body="Draft content",
        status=ArticleStatus.DRAFT,
    )

    # 4. Archived article
    Article.objects.create(
        site=site,
        author=user,
        title="Old Archived Post",
        slug="old-archived-post",
        body="Archived content",
        status=ArticleStatus.ARCHIVED,
    )

    return {
        "user": user,
        "workspace": workspace,
        "site": site,
        "inactive_site": inactive_site,
        "article1": art1,
    }


@pytest.mark.django_db
def test_sitemap_xml_contract_and_filtering(sitemap_setup: dict[str, object]) -> None:
    client = APIClient()
    site = sitemap_setup["site"]
    assert isinstance(site, Site)

    url = f"/api/v1/public/sites/{site.slug}/sitemap.xml"
    resp = client.get(url)

    assert resp.status_code == 200
    assert "application/xml" in resp.headers["Content-Type"]
    assert "Cache-Control" in resp.headers
    assert "public" in resp.headers["Cache-Control"]

    content = resp.content.decode("utf-8")
    assert "<urlset xmlns=" in content
    # Includes root URL
    assert "<loc>https://portal.example.com/</loc>" in content
    # Includes published indexable article
    assert "<loc>https://portal.example.com/articles/public-tech-report</loc>" in content
    # Excludes noindex article
    assert "private-thank-you-page" not in content
    # Excludes draft article
    assert "draft-article-post" not in content
    # Excludes archived article
    assert "old-archived-post" not in content


@pytest.mark.django_db
def test_sitemap_inactive_site_returns_404(sitemap_setup: dict[str, object]) -> None:
    client = APIClient()
    inactive_site = sitemap_setup["inactive_site"]
    assert isinstance(inactive_site, Site)

    resp = client.get(f"/api/v1/public/sites/{inactive_site.slug}/sitemap.xml")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_robots_txt_default_and_custom(sitemap_setup: dict[str, object]) -> None:
    client = APIClient()
    site = sitemap_setup["site"]
    assert isinstance(site, Site)

    url = f"/api/v1/public/sites/{site.slug}/robots.txt"

    # 1. Default robots.txt
    resp = client.get(url)
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["Content-Type"]
    content = resp.content.decode("utf-8")
    assert "User-agent: *" in content
    assert "Allow: /" in content
    assert "Sitemap: https://portal.example.com/sitemap.xml" in content

    # 2. Site with default_robots_index = False
    SiteSEOSettings.objects.update_or_create(
        site=site,
        defaults={"default_robots_index": False},
    )
    resp_disallow = client.get(url)
    content_disallow = resp_disallow.content.decode("utf-8")
    assert "Disallow: /" in content_disallow

    # 3. Custom robots.txt overrides generated content
    custom_txt = "User-agent: Googlebot\nDisallow: /private/\n\nUser-agent: *\nAllow: /\n"
    SiteSEOSettings.objects.update_or_create(
        site=site,
        defaults={"custom_robots_txt": custom_txt},
    )
    resp_custom = client.get(url)
    assert resp_custom.content.decode("utf-8").strip() == custom_txt.strip()
