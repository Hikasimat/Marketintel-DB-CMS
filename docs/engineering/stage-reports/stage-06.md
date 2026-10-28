# Stage 06 — Analytics and Privacy-Preserving Event Ingestion

- **Date:** 2026-10-28
- **Roles performed:** Sequential role passes by a single agent (Orchestrator, Security Engineer, Backend Engineer, QA, and Independent Reviewer).

## Scope

Implement GA4 configuration, authorized reporting API integrations, first-party privacy-preserving event ingestion, data retention pruning, and analytics aggregation metrics:
1. **Site Analytics & GTM Configuration (`SiteAnalyticsConfig`, ANA-1, AS-6):**
   - Measurement ID format validation (`G-XXXXXXXX`).
   - GTM Container ID format validation (`GTM-XXXXXXXX`).
   - Per-site first-party ingestion toggle (`is_first_party_enabled`, default `False` per AS-6).
   - Configurable retention periods (`retention_days`, bounded between 7 and 730 days).
   - Consent requirement flag (`require_consent`, default `True`).
   - Management endpoints (`GET`, `PATCH /api/v1/workspaces/<ws_id>/sites/<site_id>/analytics/config/`).
   - Public frontend configuration endpoint (`GET /api/v1/public/sites/<site_slug>/analytics-config`) returning only non-secret IDs, protected by CT-6 browser Origin checks.
2. **GA4 Authorized Connection & Reporting API (`GA4Connection`, `GA4ReportingAdapter`, ANA-2, ANA-3):**
   - Numeric GA4 property ID validation (`validate_ga4_property_id`).
   - Encrypted OAuth credential storage at rest using AES-256-GCM envelope encryption (SEC-3).
   - Management endpoints (`GET`, `POST`, `DELETE /api/v1/workspaces/<ws_id>/sites/<site_id>/analytics/ga4/`) with write-only credentials fields preventing secret leakage in API responses.
   - Isolated `GA4ReportingAdapter` communicating with Google Analytics Data API v1beta (`properties/{id}:runReport`), handling metric and dimension header parsing, 429 quota errors, and standard report views (overview, traffic sources, top pages).
   - Cached report snapshots (`AnalyticsReportSnapshot`) avoiding upstream quota exhaustion; query parameter `use_cache=True/False` and async background task `refresh_ga4_report_snapshot`.
   - Date range validation (maximum 365-day query window; start date before or on end date).
3. **First-Party Privacy-Preserving Event Ingestion (`AnalyticsEvent`, ANA-4, ANA-5):**
   - Public ingestion endpoint (`POST /api/v1/public/sites/<site_slug>/events`), accepting allowlisted event types only (`page_view`, `cta_click`, `form_submit`). Non-allowlisted event types rejected with HTTP 400 Bad Request.
   - Allowlisted property enforcement per event type; arbitrary property keys rejected.
   - PII detection and rejection: automated scanning rejects properties containing email addresses, phone numbers, or SSN patterns.
   - PII query string sanitization: automated stripping of `email=`, `token=`, `ssn=` query params from paths and referrers.
   - HTML and script injection rejection: payloads containing `<script>` or HTML tags are rejected with HTTP 400.
   - **Zero Raw IP Storage Guarantee (ANA-5):** `AnalyticsEvent` schema explicitly excludes IP address columns; no IP is ever persisted in database tables.
   - **User-Agent Coarsening (ANA-5):** Raw User-Agent strings are parsed and reduced strictly to coarse device categories (`DESKTOP`, `MOBILE`, `TABLET`, `BOT`, `UNKNOWN`) and browser families (`CHROME`, `FIREFOX`, `SAFARI`, `EDGE`, `OTHER`); raw UA is immediately discarded.
   - Pseudonymous identifiers only (`visitor_id`, `session_id`).
4. **Consent Gating Contract (ANA-6):**
   - If `require_consent=True`, events missing `consent_granted=True` are rejected with HTTP 403 Forbidden.
   - Consented events record `consent_basis="EXPLICIT_CONSENT"`. When consent is not required, records `consent_basis="LEGITIMATE_INTEREST"`.
5. **Data Retention & Aggregated Reporting (ANA-7):**
   - Automated Celery task `cleanup_expired_events` pruning events older than the site's configured `retention_days` and deleting expired report snapshots.
   - GDPR Art. 17 right to erasure endpoint (`DELETE /api/v1/workspaces/<ws_id>/sites/<site_id>/analytics/first-party/visitors/<visitor_id>/`) deleting all records for a visitor ID while preserving other analytics data.
   - Tenant-scoped first-party overview endpoint (`GET /api/v1/workspaces/<ws_id>/sites/<site_id>/analytics/first-party/overview/`) providing aggregated summaries, daily time-series buckets, top visited paths, and device breakdowns.
6. **Multi-Tenant Security & Anti-Enumeration (TEN-3):**
   - Cross-tenant access to analytics configs, connections, reports, and erasure endpoints returns HTTP 404 Not Found.

## Baseline (from Stage 05 commit `c6709dc`)

| Item | Finding |
|------|---------|
| Git commit | `c6709dc` ("Stage 5: search engine integrations, encrypted credentials, publishing jobs, tests") |
| Services | PostgreSQL 16 on 55432, Redis 7 on 56379 running healthy in Docker Compose |
| Test suite | 115 tests passing |

## Files Created and Modified

### Analytics App (`apps/analytics`)
- `apps/analytics/apps.py`: Registered `AnalyticsConfig`.
- `apps/analytics/models.py`: `SiteAnalyticsConfig`, `GA4Connection`, `AnalyticsEvent` (no IP field), and `AnalyticsReportSnapshot`.
- `apps/analytics/validators.py`: Format validators for GA4 measurement ID, GTM container ID, and property ID; PII detection; HTML script injection defense; query string sanitizer; and UA coarsener.
- `apps/analytics/adapters/ga4.py`: `GA4ReportingAdapter` for Google Analytics Data API v1beta.
- `apps/analytics/adapters/__init__.py`: Exported adapters package.
- `apps/analytics/tasks.py`: Celery tasks for retention cleanup (`cleanup_expired_events`) and background report caching (`refresh_ga4_report_snapshot`).
- `apps/analytics/services.py`: Event ingestion logic, database aggregation rollups, and visitor erasure.
- `apps/analytics/serializers.py`: DRF serializers for configurations, write-only credentials, public loaders, event ingestion, and reports.
- `apps/analytics/views.py`: Management views (`SiteAnalyticsConfigView`, `GA4ConnectionView`, `GA4ReportView`, `FirstPartyOverviewReportView`, `VisitorDataErasureView`) and public endpoints (`PublicAnalyticsConfigView`, `PublicEventIngestView`).
- `apps/analytics/urls.py`: Management and public URL patterns.
- `apps/analytics/migrations/0001_initial.py`: Applied database schema.

### Core Configuration & Security
- `cms/settings/base.py`: Registered `apps.analytics` in `INSTALLED_APPS` and added `AnalyticsEventTypeEnum` and `AnalyticsDeviceCategoryEnum` to `SPECTACULAR_SETTINGS.ENUM_NAME_OVERRIDES`.
- `cms/urls.py`: Mounted `apps.analytics.urls`.
- `apps/integrations/urls.py`: Refined IndexNow key file route to `[^/]+\.txt$` via `re_path`, preventing route interception of public analytics endpoints.
- `tests/security/test_idor.py`: Expanded with cross-tenant IDOR tests for all analytics endpoints.

### Test Suites (`tests/analytics`)
- `tests/analytics/test_config.py`: Format validation and public config delivery (ANA-1).
- `tests/analytics/test_ga4_oauth.py`: GA4 connection, property validation, AES-256-GCM credentials encryption at rest (ANA-2).
- `tests/analytics/test_ga4_reports.py`: GA4 Data API contract, quota error handling, snapshot caching, background tasks (ANA-3).
- `tests/analytics/test_ingest.py`: Allowlisted event ingestion, property restrictions, XSS/HTML rejection, site toggle (ANA-4).
- `tests/analytics/test_privacy.py`: Zero IP column verification, UA coarsening, PII pattern rejection, query sanitization (ANA-5).
- `tests/analytics/test_consent_gating.py`: Explicit consent enforcement and legitimate interest tracking (ANA-6).
- `tests/analytics/test_retention.py`: Retention cleanup Celery task, GDPR erasure, first-party aggregated overview (ANA-7).

## Requirements Verification Matrix

| Requirement | Implementation | Test Coverage | Status |
|-------------|----------------|---------------|--------|
| **ANA-1** (Analytics Config) | `SiteAnalyticsConfig` + public loader endpoint with Origin allowlist | `tests/analytics/test_config.py` (4 tests) | PASS |
| **ANA-2** (GA4 OAuth & Connection) | `GA4Connection` with write-only credentials encrypted with AES-256-GCM | `tests/analytics/test_ga4_oauth.py` (3 tests) | PASS |
| **ANA-3** (GA4 Reporting & Caching) | `GA4ReportingAdapter` + `AnalyticsReportSnapshot` with 6h cache and background refresh | `tests/analytics/test_ga4_reports.py` (4 tests) | PASS |
| **ANA-4** (First-Party Ingestion) | Allowlisted events (`page_view`, `cta_click`, `form_submit`), property checks, HTML rejection | `tests/analytics/test_ingest.py` (4 tests) | PASS |
| **ANA-5** (Privacy Guarantees) | Zero raw IP columns, User-Agent coarsened to device/browser, PII regex rejection | `tests/analytics/test_privacy.py` (5 tests) | PASS |
| **ANA-6** (Consent Gating) | Ingestion rejects missing consent when required; records explicit vs legitimate interest basis | `tests/analytics/test_consent_gating.py` (2 tests) | PASS |
| **ANA-7** (Retention & Reports) | Celery cleanup job, GDPR Art. 17 visitor erasure, first-party overview rollups | `tests/analytics/test_retention.py` (3 tests) | PASS |
| **TEN-3** (Anti-Enumeration) | Cross-tenant access to configs, connections, reports, and erasure returns HTTP 404 | `tests/security/test_idor.py::test_cross_tenant_analytics_access_returns_404` | PASS |
| **SEC-1** (Decoupled CMS) | Zero MarketIntel imports; standalone boundary verified | `tests/test_no_marketintel_coupling.py::test_no_marketintel_internal_imports_in_source` | PASS |

## Test & Scan Results

### Test Execution & Code Coverage
```
collected 141 items
141 passed in 84.68s

Coverage: 86% total statement coverage (threshold >= 80%)
Model Coverage:
  - apps/accounts/models.py:     97%
  - apps/analytics/models.py:    91%
  - apps/audit/models.py:        94%
  - apps/content/models.py:      94%
  - apps/integrations/models.py: 100%
  - apps/seo/models.py:          95%
  - apps/sites/models.py:        96%
  - apps/tenancy/models.py:      92%
All model classes exceed the 90% coverage threshold.
```

### Static & Security Analysis
- **OpenAPI 3.0 Generation & Validation:**
  ```
  .venv/Scripts/python manage.py spectacular --validate --fail-on-warn --file openapi.yaml
  Schema generation summary: Warnings: 0, Errors: 0
  ```
- **Ruff Code Formatting:**
  `ruff format --check .` -> 143 files already formatted clean.
- **Ruff Linter:**
  `ruff check .` -> All checks passed! 0 errors.
- **Mypy Static Typing:**
  `mypy apps` -> Success: no issues found in 79 source files.
- **Bandit Security Scanner:**
  `bandit -r apps -c pyproject.toml` -> Scanned 6,496 LOC, 0 issues identified.

## Independent Review & Security Review

1. **Zero Raw IP Guarantee (ANA-5):**
   - Verified that `AnalyticsEvent` has no IP, IP address, or remote addr field defined anywhere in its model schema or database table. Neither client IP nor proxy forwarded headers are ever stored in the database.
2. **User-Agent De-Identification (ANA-5):**
   - Incoming User-Agent strings are parsed at request time into two coarse categorical values (`device_category` and `browser_family`). The raw UA string is discarded immediately and never stored, preventing browser fingerprinting.
3. **Data Erasure & GDPR Art. 17 Compliance (ANA-7):**
   - Verified the `DELETE /api/v1/workspaces/<ws_id>/sites/<site_id>/analytics/first-party/visitors/<visitor_id>/` endpoint. When a visitor requests erasure under GDPR, all events associated with that pseudonymous `visitor_id` are purged, while logging an immutable audit event documenting the action.
4. **Credential Isolation (SEC-3):**
   - GA4 OAuth tokens are serialized into JSON and encrypted using AES-256-GCM envelope encryption before persistence. The `credentials` field on `GA4ConnectionSerializer` is strictly write-only, ensuring tokens are never leaked to viewers or analysts in API responses.

## Stage 06 Gate Decision

- **Gate Status:** `PASS`
- **Rationale:** All functional and security requirements for Stage 06 (Site analytics config, GA4 OAuth connection and Data API reporting, first-party privacy-preserving event ingestion without IP storage, consent gating, retention pruning, GDPR erasure, and IDOR protection) are fully implemented and verified by 141 passing tests at 86% total statement coverage (91% on analytics models) with zero warnings or errors across all static/security tools.
- **Next Stage:** Stage 07 — Consent Backend (Consent configurations, categories, policy versioning, consent records, withdrawal, retention, and browser integration API contracts).
