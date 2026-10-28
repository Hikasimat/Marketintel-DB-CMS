"""Tests for site and article SEO metadata, canonicals, JSON-LD, and public SEO API.

Requirements satisfied: SEO-1, SEO-2, SEO-3, SEO-9.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.content.models import Article, ArticleStatus
from apps.seo.models import SiteSEOSettings
from apps.seo.services import resolve_article_seo
from apps.seo.validators import (
    escape_jsonld_for_html,
    validate_canonical_url,
    validate_jsonld_schema,
)
from apps.sites.models import Domain, Site
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole


@pytest.fixture
def seo_setup(db: None) -> dict[str, object]:
    owner = User.objects.create_user(email="owner@seo.com", password="SecurePassword123!")
    editor = User.objects.create_user(email="editor@seo.com", password="SecurePassword123!")
    analyst = User.objects.create_user(email="analyst@seo.com", password="SecurePassword123!")

    workspace = Workspace.objects.create(name="SEO Org", slug="seo-org")
    WorkspaceMembership.objects.create(workspace=workspace, user=owner, role=WorkspaceRole.OWNER)
    WorkspaceMembership.objects.create(workspace=workspace, user=editor, role=WorkspaceRole.EDITOR)
    WorkspaceMembership.objects.create(
        workspace=workspace, user=analyst, role=WorkspaceRole.ANALYST
    )

    site = Site.objects.create(
        workspace=workspace,
        name="Global News",
        slug="global-news",
        allowed_origins=["https://news.example.com"],
        is_active=True,
    )
    domain = Domain.objects.create(
        site=site, hostname="news.example.com", is_verified=True, is_primary=True
    )

    article = Article.objects.create(
        site=site,
        author=editor,
        title="Breaking News Story",
        slug="breaking-news-story",
        excerpt="Short summary for breaking news.",
        body="Full article body content.",
        status=ArticleStatus.PUBLISHED,
    )

    return {
        "owner": owner,
        "editor": editor,
        "analyst": analyst,
        "workspace": workspace,
        "site": site,
        "domain": domain,
        "article": article,
    }


@pytest.mark.django_db
def test_canonical_url_validator(seo_setup: dict[str, object]) -> None:
    site = seo_setup["site"]
    assert isinstance(site, Site)

    # 1. Relative path passes
    assert validate_canonical_url("/articles/my-story", site) == "/articles/my-story"

    # 2. Absolute URL on registered domain passes
    valid_abs = "https://news.example.com/articles/breaking-news-story"
    assert validate_canonical_url(valid_abs, site) == valid_abs

    # 3. Invalid scheme fails
    with pytest.raises(ValidationError, match="http or https scheme"):
        validate_canonical_url("ftp://news.example.com/file", site)

    # 4. Foreign domain not in site's registered domains or allowed_origins fails
    with pytest.raises(ValidationError, match="does not match any registered or allowed domain"):
        validate_canonical_url("https://malicious-hijack.org/articles/story", site)


@pytest.mark.django_db
def test_jsonld_validation_and_safe_escaping() -> None:
    # 1. Valid Article JSON-LD
    valid_schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": "Safe JSON-LD Handling",
        "description": "Safe escaping test",
    }
    assert validate_jsonld_schema(valid_schema) == valid_schema

    # 2. Missing @context fails
    with pytest.raises(ValidationError, match="@context"):
        validate_jsonld_schema({"@type": "Article", "headline": "Test"})

    # 3. Disallowed @type fails
    with pytest.raises(ValidationError, match="Unsupported or missing JSON-LD '@type'"):
        validate_jsonld_schema({"@context": "https://schema.org", "@type": "SoftwareApplication"})

    # 4. Escaping prevents </script> injection
    hostile_schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": "Attacker </script><script>alert(1)</script>",
    }
    escaped = escape_jsonld_for_html(hostile_schema)
    assert "</script>" not in escaped
    assert "<\\/script>" in escaped


@pytest.mark.django_db
def test_site_seo_settings_api(seo_setup: dict[str, object]) -> None:
    client = APIClient()
    owner = seo_setup["owner"]
    analyst = seo_setup["analyst"]
    workspace = seo_setup["workspace"]
    site = seo_setup["site"]
    assert isinstance(workspace, Workspace)
    assert isinstance(site, Site)

    url = reverse(
        "seo:site_seo_settings", kwargs={"workspace_id": workspace.id, "site_id": site.id}
    )

    # Analyst can read (200)
    client.force_authenticate(user=analyst)
    get_resp = client.get(url)
    assert get_resp.status_code == status.HTTP_200_OK
    assert get_resp.json()["default_robots_index"] is True

    # Analyst cannot update (403)
    patch_resp_analyst = client.patch(url, {"title_suffix": " | Global News"})
    assert patch_resp_analyst.status_code == status.HTTP_403_FORBIDDEN

    # Owner can update (200)
    client.force_authenticate(user=owner)
    patch_resp = client.patch(
        url,
        {
            "title_suffix": " | Global News Network",
            "default_meta_description": "Global News covers world events as they happen.",
        },
    )
    assert patch_resp.status_code == status.HTTP_200_OK
    data = patch_resp.json()
    assert data["title_suffix"] == " | Global News Network"
    assert data["default_meta_description"] == "Global News covers world events as they happen."


@pytest.mark.django_db
def test_article_seo_metadata_api_and_resolution(seo_setup: dict[str, object]) -> None:
    client = APIClient()
    editor = seo_setup["editor"]
    workspace = seo_setup["workspace"]
    site = seo_setup["site"]
    article = seo_setup["article"]
    assert isinstance(workspace, Workspace)
    assert isinstance(site, Site)
    assert isinstance(article, Article)

    # Configure site title suffix first
    SiteSEOSettings.objects.update_or_create(
        site=site,
        defaults={
            "title_suffix": " | Global News",
            "default_meta_description": "Default site description.",
        },
    )

    url = reverse(
        "seo:article_seo",
        kwargs={"workspace_id": workspace.id, "site_id": site.id, "article_id": article.id},
    )

    client.force_authenticate(user=editor)

    # 1. Update article SEO
    patch_resp = client.patch(
        url,
        {
            "meta_title": "Breaking: Market Update",
            "meta_description": "Custom detailed description of the market.",
            "canonical_url": "https://news.example.com/articles/breaking-news-story",
            "robots_index": True,
            "robots_follow": True,
            "og_title": "Breaking: Market Update on Social",
            "twitter_card": "summary_large_image",
            "jsonld_schema": {
                "@context": "https://schema.org",
                "@type": "NewsArticle",
                "headline": "Breaking: Market Update",
            },
        },
        format="json",
    )
    assert patch_resp.status_code == status.HTTP_200_OK

    # 2. Test service resolution
    article.refresh_from_db()
    resolved = resolve_article_seo(article)
    assert resolved["title"] == "Breaking: Market Update | Global News"
    assert resolved["meta_description"] == "Custom detailed description of the market."
    assert resolved["canonical_url"] == "https://news.example.com/articles/breaking-news-story"
    assert resolved["robots"] == "index, follow"
    assert resolved["open_graph"]["title"] == "Breaking: Market Update on Social"
    assert resolved["twitter"]["card"] == "summary_large_image"
    assert resolved["json_ld"]["@type"] == "NewsArticle"
    assert "json_ld_html" in resolved


@pytest.mark.django_db
def test_public_article_seo_endpoint(seo_setup: dict[str, object]) -> None:
    client = APIClient()
    site = seo_setup["site"]
    article = seo_setup["article"]
    assert isinstance(site, Site)
    assert isinstance(article, Article)

    url = f"/api/v1/public/sites/{site.slug}/articles/{article.slug}/seo/"

    # 1. Allowed origin passes
    resp = client.get(url, HTTP_ORIGIN="https://news.example.com")
    assert resp.status_code == status.HTTP_200_OK
    assert "ETag" in resp.headers
    assert "Cache-Control" in resp.headers
    data = resp.json()
    assert data["title"] == "Breaking News Story"
    assert data["robots"] == "index, follow"

    # 2. Disallowed origin rejected (CT-6)
    forbidden_resp = client.get(url, HTTP_ORIGIN="https://unauthorized-origin.com")
    assert forbidden_resp.status_code == status.HTTP_403_FORBIDDEN

    # 3. Server-side fetch (no Origin header) passes
    ssr_resp = client.get(url)
    assert ssr_resp.status_code == status.HTTP_200_OK
