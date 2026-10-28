# Stage 04 — SEO Engine and Rendering Contracts

- **Date:** 2026-10-28
- **Roles performed:** Sequential role passes by a single agent (Orchestrator, Security Engineer, Backend Engineer, QA, and Independent Reviewer).

## Scope

Implement the complete SEO metadata, redirection, indexing feeds, and audit diagnostics engine:
1. Site-wide SEO defaults (`SiteSEOSettings`) with title suffix/template, default meta description, default robots directives, default OG image, and custom robots.txt support (SEO-1, SEO-6).
2. Article-level SEO metadata (`ArticleSEO`) with meta title, description, canonical URL, robots index/follow flags, OpenGraph tags, Twitter Card metadata, and custom JSON-LD schema (SEO-1).
3. Canonical URL validation (`validate_canonical_url`) enforcing absolute HTTPS/HTTP URLs belonging to the site's registered custom domains or relative paths, prohibiting foreign host poisoning (SEO-2).
4. Safe JSON-LD structured data engine (`validate_jsonld_schema`, `escape_jsonld_for_html`) supporting allowlisted Schema.org types (`Article`, `NewsArticle`, `BlogPosting`, etc.) and safely neutralizing `</script>` tag breakout injection and Unicode U+2028/U+2029 line terminators (SEO-3).
5. Redirect management engine (`RedirectRule`) with full graph traversal cycle/loop detection (immediate self-loops, 2-hop cycles, deep multi-hop loops), strict 5-hop chain depth bounds, and open-redirect protection restricting external redirect destinations to site domains or allowed origins (SEO-4).
6. Dynamic RFC-compliant XML sitemap generation (`GET /api/v1/public/sites/<site_slug>/sitemap.xml`) including site root and only published, active, indexable articles (`robots_index=True`), with XML character escaping, 50k URL bounds, and `Cache-Control: public, max-age=300` headers (SEO-5).
7. Dynamic `robots.txt` delivery (`GET /api/v1/public/sites/<site_slug>/robots.txt`) with custom rules or dynamic generation linking to the site's primary sitemap (SEO-6).
8. Automated SEO diagnostics audit endpoint (`GET /api/v1/workspaces/<workspace_id>/sites/<site_id>/seo-audit/`) evaluating all site articles against search engine best practices (title length > 60 chars, description missing or > 160 chars, missing social preview images, and published articles with noindex flags) (SEO-7).
9. Public article SEO metadata feed (`GET /api/v1/public/sites/<site_slug>/articles/<article_slug>/seo/`) delivering resolved title templates, meta tags, OpenGraph, Twitter Cards, canonicals, and escaped JSON-LD scripts for frontend SSR adapters, protected by CT-6 Origin allowlist checks and deterministic ETags (SEO-9).
10. Multi-tenant anti-enumeration (TEN-3) and cross-tenant IDOR protection verified for all SEO management endpoints.

## Baseline (from Stage 03 commit `1fc2e83`)

| Item | Finding |
|------|---------|
| Git commit | `1fc2e83` ("Stage 3: sites, custom domains, article versioning, content delivery API, tests") |
| Services | PostgreSQL 16 on 55432, Redis 7 on 56379 running healthy in Docker Compose |
| Test suite | 67 tests passing |

## Files Created and Modified

### SEO Engine (`apps/seo`)
- `apps/seo/apps.py`: Registered `SeoConfig`.
- `apps/seo/models.py`: `SiteSEOSettings`, `ArticleSEO`, and `RedirectRule` models.
- `apps/seo/validators.py`: Canonical URL validator, graph-traversal redirect cycle and chain depth validator, JSON-LD schema validator, and safe HTML script escaper.
- `apps/seo/services.py`: `generate_sitemap_xml`, `generate_robots_txt`, `resolve_article_seo`, and `run_seo_audit`.
- `apps/seo/serializers.py`: `SiteSEOSettingsSerializer`, `ArticleSEOSerializer`, `RedirectRuleSerializer`, `SEOAuditItemSerializer`, and `PublicSEOMetadataSerializer`.
- `apps/seo/views.py`: Management views (`SiteSEOSettingsView`, `ArticleSEOView`, `RedirectRuleListCreateView`, `RedirectRuleDetailView`, `SEOAuditView`) and public endpoints (`PublicSitemapXmlView`, `PublicRobotsTxtView`, `PublicArticleSEOView`).
- `apps/seo/urls.py`: Management routing under `/api/v1/workspaces/<workspace_id>/sites/<site_id>/` and public routes under `/api/v1/public/sites/<site_slug>/`.
- `apps/seo/migrations/0001_initial.py`: Applied database schema.

### Global Configuration & Tests
- `cms/settings/base.py`: Registered `apps.seo` in `INSTALLED_APPS`.
- `cms/urls.py`: Mounted SEO routes into the root API router.
- `tests/seo/test_seo_metadata.py`: Unit and API tests for settings, metadata resolution, canonical validation, JSON-LD safe escaping, and public SEO endpoint.
- `tests/seo/test_redirects.py`: Tests for 301/302/307/308 redirects, self-loops, circular loops, multi-hop chains, and open-redirect defense.
- `tests/seo/test_sitemap_and_robots.py`: Tests for XML sitemap generation, draft/noindex filtering, and robots.txt generation.
- `tests/seo/test_seo_audit.py`: Tests for automated SEO diagnostics.
- `tests/security/test_idor.py`: Expanded with cross-tenant IDOR tests for SEO endpoints.

## Requirements Verification Matrix

| Requirement | Implementation | Test Coverage | Status |
|-------------|----------------|---------------|--------|
| **SEO-1** (Page & Site SEO) | `SiteSEOSettings` + `ArticleSEO` with template inheritance | `tests/seo/test_seo_metadata.py::test_article_seo_metadata_api_and_resolution` | PASS |
| **SEO-2** (Canonical validation) | `validate_canonical_url` enforcing registered domain match or relative path | `tests/seo/test_seo_metadata.py::test_canonical_url_validator` | PASS |
| **SEO-3** (Safe JSON-LD) | `validate_jsonld_schema` + `escape_jsonld_for_html` preventing script breakout | `tests/seo/test_seo_metadata.py::test_jsonld_validation_and_safe_escaping` | PASS |
| **SEO-4** (Redirects engine) | `RedirectRule` + graph cycle detection, 5-hop bound, open-redirect defense | `tests/seo/test_redirects.py` (4 tests) | PASS |
| **SEO-5** (XML Sitemap) | Dynamic XML generation excluding drafts/noindex, respecting primary domain | `tests/seo/test_sitemap_and_robots.py::test_sitemap_xml_contract_and_filtering` | PASS |
| **SEO-6** (robots.txt) | Dynamic `robots.txt` with sitemap reference or custom override | `tests/seo/test_sitemap_and_robots.py::test_robots_txt_default_and_custom` | PASS |
| **SEO-7** (SEO Audit) | Diagnostic analyzer checking title/description bounds, OG image, noindex | `tests/seo/test_seo_audit.py::test_seo_audit_diagnostics` | PASS |
| **SEO-9** (Public SEO feed) | Public endpoint delivering resolved meta/OG/Twitter/JSON-LD with ETags | `tests/seo/test_seo_metadata.py::test_public_article_seo_endpoint` | PASS |
| **TEN-3** (Anti-enumeration) | Cross-tenant access to SEO settings, articles, and redirects returns HTTP 404 | `tests/security/test_idor.py::test_cross_tenant_seo_access_returns_404` | PASS |
| **SEC-1** (No MarketIntel coupling) | Zero imports from external MarketIntel modules; standalone service verified | `tests/test_no_marketintel_coupling.py::test_no_marketintel_internal_imports_in_source` | PASS |

## Test & Scan Results

### Test Execution & Code Coverage
```
collected 81 items
81 passed in 58.78s

Coverage: 85% total (threshold >= 80%)
Model Coverage:
  - apps/accounts/models.py: 97%
  - apps/audit/models.py:    94%
  - apps/content/models.py:  94%
  - apps/seo/models.py:      95%
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
  `ruff format --check .` -> 104 files formatted clean.
- **Ruff Linter:**
  `ruff check .` -> All checks passed! 0 errors.
- **Mypy Static Typing:**
  `mypy apps` -> Success: no issues found in 55 source files.
- **Bandit Security Scanner:**
  `bandit -r apps -c pyproject.toml` -> Scanned 4,191 LOC, 0 issues identified.
- **Django Security Deployment Checks:**
  `manage.py check --deploy --settings=cms.settings.test` -> 0 critical errors, expected non-SSL warnings in test profile.

## Independent Review & Security Review

1. **XSS & Structured Data Escaping:**
   - Evaluated `escape_jsonld_for_html`. Injection payloads attempting `</script><script>alert(1)</script>` are safely escaped as `<\\/script>`, neutralizing browser DOM breakout vulnerabilities when embedded in `<script type="application/ld+json">`.
2. **Open-Redirect & Phishing Defense:**
   - Redirect rules strictly validate that target URLs are either relative paths or point to registered domains for the site or authorized partner origins. External phishing destinations are rejected with HTTP 400 Bad Request.
3. **Infinite Loop & Resource Exhaustion Defense:**
   - The redirect engine conducts a full graph traversal across all active site routes upon rule creation or update. Any cycle (e.g. A->B->A or A->B->C->A) or chain exceeding 5 hops is proactively rejected.
4. **Sitemap Freshness & Privacy:**
   - The XML sitemap dynamically queries PostgreSQL at request time, excluding non-published drafts, archived articles, and private pages explicitly marked `robots_index=False`.

## Stage 04 Gate Decision

- **Gate Status:** `PASS`
- **Rationale:** All functional and security requirements for Stage 04 (SEO Engine, Canonicals, Safe JSON-LD, Redirects, Sitemap, robots.txt, SEO Audit, and Public SEO Metadata) are fully implemented, verified by 81 passing automated tests, covered at 85% total statement coverage (>=92% on all model definitions), and validated with zero warnings or errors across all static/security tools.
- **Next Stage:** Stage 05 — Search Provider Integrations (Google Search Console, Bing Webmaster Tools, IndexNow, encrypted credentials, retry/rate-limit policies, idempotency, and publishing notifications).
