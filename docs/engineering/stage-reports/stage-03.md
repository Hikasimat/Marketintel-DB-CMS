# Stage 03 — Sites, Custom Domains, and Content Engine

- **Date:** 2026-10-28
- **Roles performed:** Sequential role passes by a single agent (Orchestrator, Security Engineer, Backend Engineer, QA, and Independent Reviewer).

## Scope

Implement the multi-tenant site topology and core content management engine:
1. Multi-tenant site provisioning (`Site`) with workspace isolation, unique slug per workspace, default locale, allowed CORS origins, and theme styling configuration (SITE-1).
2. Custom domain registration (`Domain`) with RFC 1123 hostname validation, primary domain designation, and DNS TXT verification token generation (`_cms-verify.<hostname>`) (SITE-2, SITE-3).
3. Article content lifecycle (`Article` with `DRAFT`, `IN_REVIEW`, `PUBLISHED`, `ARCHIVED` statuses, unique slug per site, JSON metadata, and rich body) (CT-1, CT-2).
4. Immutable revision versioning engine (`ArticleVersion`) capturing automated delta/snapshot history on create, update, and publish, with instant rollback capabilities to any historic version (CT-3, CT-5).
5. Media asset cataloging (`MediaAsset`) with strictly enforced 10MB bounds and SHA-256 integrity checksums.
6. Public read-only content delivery API (`/api/v1/public/sites/<site_slug>/articles/` and `.../<article_slug>/`) serving only published articles on active sites with deterministic ETag and `Cache-Control: public, max-age=60` headers (CT-4).
7. Origin allowlist enforcement on public content endpoints: validating `Origin` header against site-configured `allowed_origins` (allowed origin -> HTTP 200, unauthorized origin -> HTTP 403, server-side/missing origin -> HTTP 200) (CT-6).
8. Strict cross-tenant IDOR defense: cross-workspace and cross-site access attempts return HTTP 404 Not Found to prevent enumeration.

## Baseline (from Stage 02 commit `b3c3439`)

| Item | Finding |
|------|---------|
| Git commit | `b3c3439` ("Stage 2: authentication, tenancy, RBAC, audit logging, tests") |
| Services | PostgreSQL 16 on 55432, Redis 7 on 56379 running healthy in Docker Compose |
| Test suite | 54 tests passing |

## Files Created and Modified

### Sites & Domains Engine (`apps/sites`)
- `apps/sites/models.py`: `Site` and `Domain` models with verification tokens, SSL status tracking, and primary domain resolution.
- `apps/sites/validators.py`: RFC 1123 hostname validator rejecting protocols, ports, paths, IP binding targets, and reserved names.
- `apps/sites/serializers.py`: `SiteSerializer`, `SiteCreateSerializer`, `DomainSerializer`, `DomainCreateSerializer`, and `DomainVerifyRequestSerializer`.
- `apps/sites/views.py`: Management views (`SiteListCreateView`, `SiteDetailView`, `DomainListCreateView`, `DomainDetailView`, `DomainVerifyView`).
- `apps/sites/urls.py`: Nested routing under `/api/v1/workspaces/<workspace_id>/sites/`.
- `apps/sites/migrations/0001_initial.py`: Applied migration schema.

### Content Engine & Public Delivery (`apps/content`)
- `apps/content/models.py`: `Article`, `ArticleVersion` (immutable revision history), and `MediaAsset` (10MB bounded catalog).
- `apps/content/services.py`: `create_article_version`, `publish_article`, and `restore_article_version` services with audit trail recording.
- `apps/content/serializers.py`: `ArticleSerializer`, `ArticleCreateUpdateSerializer`, `ArticleVersionSerializer`, `MediaAssetSerializer`, `MediaAssetCreateSerializer`, and `PublicArticleSerializer`.
- `apps/content/views.py`: Management CRUD views, revision restore views, media catalog views, and public delivery views (`PublicArticleListView`, `PublicArticleDetailView`) with Origin allowlist validation.
- `apps/content/urls.py`: Content management routing under `/api/v1/workspaces/<workspace_id>/sites/<site_id>/` and public delivery under `/api/v1/public/sites/<site_slug>/articles/`.
- `apps/content/migrations/0001_initial.py`: Applied migration schema.

### Global Configuration & Tests
- `cms/settings/base.py`: Registered `apps.sites` and `apps.content` in `INSTALLED_APPS`.
- `cms/urls.py`: Mounted sites and content routes into the root API router.
- `tests/sites/test_sites_domains.py`: Comprehensive test suite for hostname validation, site lifecycle, domain registration, and TXT verification.
- `tests/content/test_article_lifecycle.py`: Test suite for article CRUD, automated versioning, publishing, and revision rollback.
- `tests/content/test_public_content_api.py`: Test suite for public article delivery, cache headers (ETag, Cache-Control), status filtering, and CT-6 Origin header enforcement.
- `tests/security/test_idor.py`: Expanded with cross-tenant and cross-site isolation tests for Sites, Domains, Articles, and MediaAssets.

## Requirements Verification Matrix

| Requirement | Implementation | Test Coverage | Status |
|-------------|----------------|---------------|--------|
| **SITE-1** (Multi-tenant sites) | `Site` model scoped to `Workspace`, unique slug per workspace, theme configuration | `tests/sites/test_sites_domains.py::test_site_lifecycle_and_rbac` | PASS |
| **SITE-2** (Custom domains) | `Domain` model with RFC 1123 validation, single primary domain per site | `tests/sites/test_sites_domains.py::test_domain_registration_and_verification` | PASS |
| **SITE-3** (Domain verification) | Generated TXT verification token, verify API endpoint | `tests/sites/test_sites_domains.py::test_domain_registration_and_verification` | PASS |
| **CT-1** (Article data model) | `Article` model with lifecycle statuses, author FK, metadata, rich body | `tests/content/test_article_lifecycle.py::test_article_lifecycle_and_versioning` | PASS |
| **CT-2** (Slug uniqueness per site) | `unique_together = ("site", "slug")` in `Article` model and serializer validation | `tests/content/test_article_lifecycle.py::test_article_lifecycle_and_versioning` | PASS |
| **CT-3** (Immutable versioning) | `ArticleVersion` snapshots created on every revision and publish action | `tests/content/test_article_lifecycle.py::test_article_lifecycle_and_versioning` | PASS |
| **CT-4** (Public delivery API) | Public read-only endpoints returning only published articles on active sites | `tests/content/test_public_content_api.py::test_public_articles_list_only_published` | PASS |
| **CT-5** (Version rollback) | `restore_article_version` service creating new version snapshot from prior state | `tests/content/test_article_lifecycle.py::test_article_lifecycle_and_versioning` | PASS |
| **CT-6** (Origin allowlisting) | `_check_public_origin_allowlist` validating Origin against `site.allowed_origins` | `tests/content/test_public_content_api.py::test_public_origin_allowlist_enforcement` | PASS |
| **TEN-3** (Anti-enumeration) | Cross-tenant and cross-site access return HTTP 404 Not Found, never 403 | `tests/security/test_idor.py` (7 tests) | PASS |
| **SEC-1** (No MarketIntel coupling) | Zero imports from external MarketIntel modules; standalone service verified | `tests/test_no_marketintel_coupling.py::test_no_marketintel_imports_in_apps` | PASS |

## Test & Scan Results

### Test Execution & Code Coverage
```
collected 67 items
67 passed in 42.53s

Coverage: 84% total (threshold >= 80%)
Model Coverage:
  - apps/accounts/models.py: 97%
  - apps/audit/models.py:    94%
  - apps/content/models.py:  94%
  - apps/sites/models.py:    96%
  - apps/tenancy/models.py:  92%
All model classes exceed the 90% coverage threshold.
```

### Static & Security Analysis
- **OpenAPI 3.0 Generation & Validation:**
  ```
  .venv/Scripts/python manage.py spectacular --validate --fail-on-warn --file openapi.yaml
  Schema generation summary: Warnings: 0, Errors: 0
  ```
- **Ruff Code Formatting:**
  `ruff format --check .` -> 91 files formatted clean.
- **Ruff Linter:**
  `ruff check .` -> All checks passed! 0 errors.
- **Mypy Static Typing:**
  `mypy apps` -> Success: no issues found in 47 source files.
- **Bandit Security Scanner:**
  `bandit -r apps -c pyproject.toml` -> Scanned 3,147 LOC, 0 issues identified.
- **Django Security Deployment Checks:**
  `manage.py check --deploy --settings=cms.settings.test` -> 0 critical errors, expected non-SSL warnings in test profile.

## Independent Review & Security Review

1. **RFC 1123 Hostname Validation:**
   - Hostname validator prevents injection, URL path traversal, and SSRF by prohibiting schemes (`http://`), ports (`:8080`), paths (`/test`), IP loopback addresses (`127.0.0.1`, `0.0.0.0`), and reserved domain suffixes.
2. **CORS & Origin Header Verification (CT-6):**
   - The public delivery API strictly validates the incoming browser `Origin` header against `site.allowed_origins`. Unauthorized domains receive HTTP 403 Forbidden with clear error envelopes. Requests without an `Origin` header (such as server-side rendering pipelines or backend microservices) are cleanly allowed.
3. **Audit Logging Coverage:**
   - All critical mutations emit immutable audit records: `site.created`, `site.updated`, `site.deleted`, `domain.registered`, `domain.verified`, `domain.deleted`, `article.created`, `article.updated`, `article.published`, `article.version_restored`, `article.deleted`, and `media.uploaded`.
4. **ETag & Cache Header Freshness:**
   - Public content endpoints return `Cache-Control: public, max-age=60` and deterministic SHA-256 ETags based on article ID and timestamp to enable HTTP 304 Not Modified caching on client CDNs.

## Stage 03 Gate Decision

- **Gate Status:** `PASS`
- **Rationale:** All functional and security requirements for Stage 03 (Sites, Domains, Content Engine, Versioning, Public Delivery, Origin Allowlisting) are implemented, verified by 67 passing automated tests, covered at 84% total codebase coverage (>=92% on all model definitions), and validated with zero warnings or errors across all static/security tools.
- **Next Stage:** Stage 04 — SEO Engine (canonical URL resolution, meta tags, OpenGraph/Twitter Cards, JSON-LD Schema.org generators, and dynamic XML sitemap generation).
