"""Django management command to seed a complete sample test publication site."""

from __future__ import annotations

from datetime import timedelta
import random
from typing import Any

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import User
from apps.analytics.models import AnalyticsEvent, DeviceCategory, EventType, SiteAnalyticsConfig
from apps.content.models import Article, ArticleStatus, ArticleVersion, ContentType
from apps.seo.models import ArticleSEO, SiteSEOSettings
from apps.sites.models import Domain, Site
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole


class Command(BaseCommand):
    help = "Seed database with a complete demo publication site, articles, SEO, and analytics."

    def handle(self, *args: Any, **options: Any) -> None:
        self.stdout.write(self.style.NOTICE("Seeding demo publication data..."))

        # 1. Admin User
        user, _ = User.objects.get_or_create(
            email="admin@cms.local",
            defaults={"is_staff": True, "is_superuser": True},
        )
        user.set_password("AdminPassword123!")
        user.save()
        self.stdout.write(self.style.SUCCESS(f"[OK] User ready: {user.email}"))

        # 2. Workspace
        workspace, _ = Workspace.objects.get_or_create(
            slug="primary-workspace",
            defaults={"name": "Primary Workspace"},
        )
        WorkspaceMembership.objects.get_or_create(
            workspace=workspace,
            user=user,
            defaults={"role": WorkspaceRole.OWNER},
        )
        self.stdout.write(self.style.SUCCESS(f"[OK] Workspace ready: {workspace.name} ({workspace.id})"))

        # 3. Site
        site, _ = Site.objects.get_or_create(
            workspace=workspace,
            slug="techradar-demo",
            defaults={
                "name": "TechRadar Demo",
                "default_locale": "en-US",
                "allowed_origins": ["*"],
                "settings": {"theme": "dark", "description": "Cutting edge engineering news"},
            },
        )
        site.allowed_origins = ["*"]
        site.save()
        self.stdout.write(self.style.SUCCESS(f"[OK] Site ready: {site.name} (slug: {site.slug})"))

        # 4. Custom Domain
        Domain.objects.get_or_create(
            site=site,
            hostname="demo.techradar.dev",
            defaults={
                "is_primary": True,
                "is_verified": True,
                "ssl_status": "ACTIVE",
            },
        )

        # 5. Site SEO Settings
        SiteSEOSettings.objects.get_or_create(
            site=site,
            defaults={
                "title_suffix": " | TechRadar Demo",
                "default_meta_description": (
                    "Enterprise insights on cloud engineering and autonomous AI architectures."
                ),
                "default_robots_index": True,
                "default_robots_follow": True,
            },
        )

        # 6. Site Analytics Config
        SiteAnalyticsConfig.objects.get_or_create(
            site=site,
            defaults={
                "is_first_party_enabled": True,
                "require_consent": False,
                "retention_days": 90,
            },
        )

        # 7. Articles & Revisions
        now = timezone.now()

        articles_data = [
            {
                "title": "Autonomous AI Coding Agents in 2026",
                "slug": "autonomous-ai-coding-agents-2026",
                "excerpt": "An in-depth look at multi-stage verification workflows transforming software development.",
                "body": (
                    "# Autonomous AI Coding Agents in 2026\n\n"
                    "Software development is rapidly evolving from manual coding to specification-guided, "
                    "self-verifying autonomous agents. By pairing LLMs with deterministic linters, static analyzers, "
                    "and automated testing suites, development teams achieve 10x throughput with zero regression debt.\n\n"
                    "## Key Pillars of Reliable Agent Systems\n"
                    "1. Fail-fast schema validation\n"
                    "2. Immutable audit trails\n"
                    "3. Comprehensive regression suites\n"
                ),
                "status": ArticleStatus.PUBLISHED,
                "published_at": now - timedelta(days=2),
                "seo_title": "Autonomous AI Coding Agents in 2026 — Comprehensive Architecture Guide",
                "seo_desc": "Architectural principles, verification loops, and quality gates for autonomous AI agents.",
            },
            {
                "title": "Building High-Throughput Headless CMS Backends",
                "slug": "building-high-throughput-headless-cms-backends",
                "excerpt": "Architectural blueprint for building multi-tenant API-first headless content platforms.",
                "body": (
                    "# Building High-Throughput Headless CMS Backends\n\n"
                    "Decoupled content platforms provide unprecedented scalability, frontend freedom, and strict security isolation.\n\n"
                    "## Architectural Design\n"
                    "- Tenant-scoped data isolation\n"
                    "- Dynamic sitemap and robots.txt generation\n"
                    "- Envelope-encrypted credentials (AES-256-GCM)\n"
                ),
                "status": ArticleStatus.PUBLISHED,
                "published_at": now - timedelta(days=5),
                "seo_title": "Building High-Throughput Headless CMS Backends with Django",
                "seo_desc": "Blueprint for clean architecture, tenant isolation, and sub-50ms API delivery.",
            },
            {
                "title": "Upcoming Multi-Cloud Search Indexing Protocol",
                "slug": "upcoming-multi-cloud-search-indexing",
                "excerpt": "Draft specification for automated search engine submission workflows.",
                "body": (
                    "# Upcoming Multi-Cloud Search Indexing Protocol\n\n"
                    "This draft specification outlines direct IndexNow and Search Console push triggers upon publication."
                ),
                "status": ArticleStatus.DRAFT,
                "published_at": None,
                "seo_title": "Draft: Multi-Cloud Search Indexing",
                "seo_desc": "Draft proposal for real-time web indexing protocols.",
            },
        ]

        for item in articles_data:
            art, created = Article.objects.get_or_create(
                site=site,
                slug=item["slug"],
                defaults={
                    "author": user,
                    "title": item["title"],
                    "excerpt": item["excerpt"],
                    "body": item["body"],
                    "content_type": ContentType.POST,
                    "status": item["status"],
                    "published_at": item["published_at"],
                },
            )
            # Create snapshot version
            ArticleVersion.objects.get_or_create(
                article=art,
                version_number=1,
                defaults={
                    "title": item["title"],
                    "excerpt": item["excerpt"],
                    "body": item["body"],
                    "created_by": user,
                },
            )
            # Create SEO metadata
            ArticleSEO.objects.get_or_create(
                article=art,
                defaults={
                    "meta_title": item["seo_title"],
                    "meta_description": item["seo_desc"],
                    "canonical_url": f"https://demo.techradar.dev/articles/{item['slug']}",
                },
            )

        self.stdout.write(self.style.SUCCESS(f"[OK] Seeded {len(articles_data)} articles with SEO & revisions."))

        # 8. Sample Analytics Events
        event_types = [EventType.PAGE_VIEW, EventType.PAGE_VIEW, EventType.CTA_CLICK, EventType.FORM_SUBMIT]
        paths = ["/blog", "/articles/autonomous-ai-coding-agents-2026", "/pricing", "/contact"]
        devices = [DeviceCategory.DESKTOP, DeviceCategory.MOBILE, DeviceCategory.TABLET]

        for i in range(25):
            days_ago = random.randint(0, 6)
            occurred = now - timedelta(days=days_ago, minutes=random.randint(10, 500))
            AnalyticsEvent.objects.create(
                site=site,
                event_type=random.choice(event_types),
                visitor_id=f"visitor-seed-{i % 5:03d}",
                session_id=f"session-seed-{i % 8:03d}",
                path=random.choice(paths),
                properties={"source": "direct", "referrer": "seed"},
                device_category=random.choice(devices),
                browser_family="Chrome",
                consent_basis="LEGITIMATE_INTEREST",
                occurred_at=occurred,
            )

        self.stdout.write(self.style.SUCCESS("[OK] Seeded 25 privacy-preserving analytics events."))

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("Demo Site Ready For Testing!"))
        self.stdout.write(f"Site Name:   {site.name}")
        self.stdout.write(f"Site Slug:   {site.slug}")
        self.stdout.write(f"Workspace:   {workspace.name} ({workspace.id})")
        self.stdout.write("Public Delivery API endpoints:")
        self.stdout.write(f"  Articles List:  /api/v1/public/sites/{site.slug}/articles/")
        self.stdout.write(f"  Single Article: /api/v1/public/sites/{site.slug}/articles/autonomous-ai-coding-agents-2026")
        self.stdout.write(f"  Dynamic Sitemap:/api/v1/public/sites/{site.slug}/sitemap.xml")
        self.stdout.write(f"  Robots.txt:     /api/v1/public/sites/{site.slug}/robots.txt")
        self.stdout.write("=" * 60 + "\n")
