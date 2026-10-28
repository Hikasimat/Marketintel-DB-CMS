"""SEO business services for sitemap generation, robots.txt, metadata resolution, and SEO audits."""

from __future__ import annotations

from typing import Any

from django.utils.html import escape

from apps.content.models import Article, ArticleStatus
from apps.seo.models import ArticleSEO
from apps.seo.validators import escape_jsonld_for_html
from apps.sites.models import Site


def _get_site_base_url(site: Site) -> str:
    """Resolve base public URL for site based on verified custom domain or slug."""
    domain = site.domains.filter(is_verified=True, is_primary=True).first()
    if not domain:
        domain = site.domains.filter(is_verified=True).first()

    if domain:
        return f"https://{domain.hostname}"
    return f"https://{site.slug}.cms.local"


def generate_sitemap_xml(site: Site) -> str:
    """Generate RFC-compliant XML sitemap for indexable published articles (SEO-5)."""
    base_url = _get_site_base_url(site)

    # Exclude drafts, archived articles, and articles marked noindex
    articles = (
        Article.objects.filter(site=site, status=ArticleStatus.PUBLISHED)
        .select_related("seo")
        .order_by("-updated_at")[:50000]
    )

    url_entries: list[str] = []

    # Include site root
    site_seo = getattr(site, "seo_settings", None)
    if site_seo is None or site_seo.default_robots_index:
        url_entries.append(
            f"  <url>\n"
            f"    <loc>{escape(base_url)}/</loc>\n"
            f"    <changefreq>daily</changefreq>\n"
            f"    <priority>1.0</priority>\n"
            f"  </url>"
        )

    for article in articles:
        # Check robots_index flag
        art_seo = getattr(article, "seo", None)
        if art_seo and not art_seo.robots_index:
            continue

        loc = f"{base_url}/articles/{article.slug}"
        lastmod = article.updated_at.strftime("%Y-%m-%d")

        url_entries.append(
            f"  <url>\n"
            f"    <loc>{escape(loc)}</loc>\n"
            f"    <lastmod>{lastmod}</lastmod>\n"
            f"    <changefreq>weekly</changefreq>\n"
            f"    <priority>0.8</priority>\n"
            f"  </url>"
        )

    urls_body = "\n".join(url_entries)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls_body}\n"
        "</urlset>"
    )


def generate_robots_txt(site: Site) -> str:
    """Generate robots.txt configuration with sitemap reference (SEO-6)."""
    site_seo = getattr(site, "seo_settings", None)
    if site_seo and site_seo.custom_robots_txt.strip():
        return site_seo.custom_robots_txt.strip()

    base_url = _get_site_base_url(site)
    sitemap_url = f"{base_url}/sitemap.xml"

    lines = ["User-agent: *"]
    if site_seo and not site_seo.default_robots_index:
        lines.append("Disallow: /")
    else:
        lines.append("Allow: /")

    lines.append("")
    lines.append(f"Sitemap: {sitemap_url}")
    return "\n".join(lines)


def resolve_article_seo(article: Article) -> dict[str, Any]:
    """Resolve full SEO metadata package for site-side rendering (SEO-1, SEO-9)."""
    site = article.site
    site_seo = getattr(site, "seo_settings", None)
    art_seo = getattr(article, "seo", None)
    base_url = _get_site_base_url(site)

    # 1. Title
    suffix = site_seo.title_suffix if site_seo else ""
    meta_title = art_seo.meta_title if (art_seo and art_seo.meta_title) else article.title
    full_title = (
        f"{meta_title}{suffix}" if suffix and not meta_title.endswith(suffix) else meta_title
    )

    # 2. Meta description
    meta_description = (
        (art_seo.meta_description if art_seo and art_seo.meta_description else "")
        or article.excerpt
        or (site_seo.default_meta_description if site_seo else "")
    )

    # 3. Canonical URL
    default_canonical = f"{base_url}/articles/{article.slug}"
    canonical_url = (
        art_seo.canonical_url if art_seo and art_seo.canonical_url else ""
    ) or default_canonical

    # 4. Robots directive
    robots_index = (
        art_seo.robots_index
        if art_seo is not None
        else (site_seo.default_robots_index if site_seo else True)
    )
    robots_follow = (
        art_seo.robots_follow
        if art_seo is not None
        else (site_seo.default_robots_follow if site_seo else True)
    )
    index_str = "index" if robots_index else "noindex"
    follow_str = "follow" if robots_follow else "nofollow"
    robots_content = f"{index_str}, {follow_str}"

    # 5. OpenGraph
    og_title = (art_seo.og_title if art_seo and art_seo.og_title else "") or meta_title
    og_description = (
        art_seo.og_description if art_seo and art_seo.og_description else ""
    ) or meta_description
    og_image = (art_seo.og_image_url if art_seo and art_seo.og_image_url else "") or (
        site_seo.default_og_image_url if site_seo else ""
    )

    # 6. Twitter Cards
    twitter_card = (
        art_seo.twitter_card if art_seo and art_seo.twitter_card else "summary_large_image"
    )

    # 7. JSON-LD structured data
    jsonld_data: dict[str, Any]
    if art_seo and art_seo.jsonld_schema:
        jsonld_data = art_seo.jsonld_schema
    else:
        jsonld_data = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": meta_title,
            "description": meta_description,
            "mainEntityOfPage": {"@type": "WebPage", "@id": canonical_url},
            "datePublished": article.published_at.isoformat() if article.published_at else None,
            "dateModified": article.updated_at.isoformat(),
        }
        if article.author:
            jsonld_data["author"] = {"@type": "Person", "name": article.author.email}
        if og_image:
            jsonld_data["image"] = og_image

    return {
        "title": full_title,
        "meta_description": meta_description,
        "canonical_url": canonical_url,
        "robots": robots_content,
        "robots_index": robots_index,
        "robots_follow": robots_follow,
        "open_graph": {
            "title": og_title,
            "description": og_description,
            "image": og_image,
            "type": "article",
            "url": canonical_url,
        },
        "twitter": {
            "card": twitter_card,
            "title": og_title,
            "description": og_description,
            "image": og_image,
        },
        "json_ld": jsonld_data,
        "json_ld_html": escape_jsonld_for_html(jsonld_data),
    }


def run_seo_audit(site: Site) -> list[dict[str, Any]]:
    """Analyze site articles and emit actionable SEO diagnostics (SEO-7)."""
    diagnostics: list[dict[str, Any]] = []

    articles = Article.objects.filter(site=site).select_related("seo")
    for article in articles:
        art_seo: ArticleSEO | None = getattr(article, "seo", None)
        title = art_seo.meta_title if art_seo and art_seo.meta_title else article.title
        desc = art_seo.meta_description if art_seo and art_seo.meta_description else article.excerpt

        # Title checks
        if not title:
            diagnostics.append(
                {
                    "article_id": str(article.id),
                    "slug": article.slug,
                    "field": "title",
                    "severity": "ERROR",
                    "code": "TITLE_MISSING",
                    "message": "Article has no title or meta title.",
                    "remediation": "Provide a descriptive title between 30 and 60 characters.",
                }
            )
        elif len(title) > 60:
            diagnostics.append(
                {
                    "article_id": str(article.id),
                    "slug": article.slug,
                    "field": "meta_title",
                    "severity": "WARNING",
                    "code": "TITLE_TOO_LONG",
                    "message": (
                        f"Title length ({len(title)} chars) exceeds recommended 60 chars "
                        "and may be truncated."
                    ),
                    "remediation": "Shorten the meta title to under 60 characters.",
                }
            )

        # Meta description checks
        if not desc:
            diagnostics.append(
                {
                    "article_id": str(article.id),
                    "slug": article.slug,
                    "field": "meta_description",
                    "severity": "WARNING",
                    "code": "DESCRIPTION_MISSING",
                    "message": "Missing meta description and excerpt.",
                    "remediation": (
                        "Add an engaging meta description between 70 and 160 characters."
                    ),
                }
            )
        elif len(desc) > 160:
            diagnostics.append(
                {
                    "article_id": str(article.id),
                    "slug": article.slug,
                    "field": "meta_description",
                    "severity": "WARNING",
                    "code": "DESCRIPTION_TOO_LONG",
                    "message": f"Description length ({len(desc)} chars) exceeds 160 characters.",
                    "remediation": (
                        "Compress description to under 160 characters "
                        "for optimal search snippet display."
                    ),
                }
            )

        # OpenGraph image check
        if art_seo and not art_seo.og_image_url:
            diagnostics.append(
                {
                    "article_id": str(article.id),
                    "slug": article.slug,
                    "field": "og_image_url",
                    "severity": "INFO",
                    "code": "OG_IMAGE_MISSING",
                    "message": "No social preview image specified for this article.",
                    "remediation": "Specify an og_image_url for rich social media cards.",
                }
            )

        # Noindex warning on published articles
        if article.status == ArticleStatus.PUBLISHED and art_seo and not art_seo.robots_index:
            diagnostics.append(
                {
                    "article_id": str(article.id),
                    "slug": article.slug,
                    "field": "robots_index",
                    "severity": "INFO",
                    "code": "PUBLISHED_NOINDEX",
                    "message": (
                        "Article is published but marked noindex "
                        "(excluded from search index and sitemap)."
                    ),
                    "remediation": (
                        "Set robots_index to true if this article should appear in search results."
                    ),
                }
            )

    return diagnostics
