# Stage 05 — Search Provider Integrations and Publishing Jobs

- **Date:** 2026-10-28
- **Roles performed:** Sequential role passes by a single agent (Orchestrator, Security Engineer, Backend Engineer, QA, and Independent Reviewer).

## Scope

Implement search engine indexing integrations, encrypted credential storage, publishing notifications, and resilient background jobs:
1. **AES-256-GCM Envelope Encryption (`apps/common/crypto.py`):** Multi-tenant secret and credential encryption at rest (SEC-3). Master Key Encryption Key (KEK) derives from settings/env; each credential record generates a fresh 256-bit Data Encryption Key (DEK) with distinct 96-bit nonces for both KEK-wrapping and payload encryption. Format: `v1:<nonce_kek_b64>:<encrypted_dek_b64>:<nonce_data_b64>:<ciphertext_b64>`.
2. **Search Provider Integrations (`apps/integrations/models.py`):**
   - `SearchEngineConnection`: Multi-tenant site connection configuration supporting `GOOGLE`, `BING`, and `INDEXNOW` with encrypted API credentials (`set_credentials`, `get_credentials`), connection status, sync timestamps, and error messages.
   - `IndexNowKey`: 32-character hexadecimal verification key generation (`secrets.token_hex(16)`), key location resolution to `https://<domain>/<key>.txt`, and key rotation.
   - `IndexSubmissionLog`: Audit log of all submission attempts tracking URLs, provider, status (`PENDING`, `SUBMITTED`, `FAILED`), response codes, raw response bodies, retry counts, and SHA-256 idempotency keys (OPS-1).
3. **Isolated Search Adapters (`apps/integrations/adapters/`):**
   - `BaseSearchEngineAdapter`: Abstract interface defining `submit_sitemap`, `submit_urls`, and `inspect_url`.
   - `GoogleSearchConsoleAdapter`: Submits XML sitemaps via the Webmasters API (`PUT /webmasters/v3/sites/.../sitemaps/...`) and inspects indexing status via the URL Inspection API (`POST /v1/urlInspection/index:inspect`). Strictly disallows arbitrary article submission per official Google guidelines restricting the Indexing API exclusively to `JobPosting` and `BroadcastEvent` structured data.
   - `BingWebmasterAdapter`: Submits XML sitemaps (`/SubmitSitemap`) and batches of URLs (`/SubmitUrlbatch`) to Bing Webmaster Tools API with API key authentication.
   - `IndexNowAdapter`: Submits URL batches to `https://api.indexnow.org/indexnow` with host, key, and keyLocation; enforces maximum bound of 10,000 URLs per submission.
4. **Resilient Background Publishing Jobs (`apps/integrations/tasks.py`):**
   - Celery `submit_indexing_job` task with exponential backoff and jitter (`(2**retries) + random.uniform(0.5, 2.0)`), handling transient 429 rate-limiting and 5xx upstream errors up to 3 retries before marking as `FAILED`.
   - Idempotency deduplication window (1 hour) in `notify_search_engines_for_article` avoiding search engine spam on rapid updates.
   - Automatic `transaction.on_commit` integration in `apps/content/services.py:publish_article` enqueuing background indexing jobs upon successful article publication.
5. **Management & Public APIs (`apps/integrations/views.py`, `serializers.py`, `urls.py`):**
   - Connection management endpoints (`GET`, `POST`, `PATCH`, `DELETE`) with write-only credentials fields preventing secret leakage in API responses.
   - IndexNow key management and rotation endpoints.
   - Manual URL batch submission endpoint validating that submitted URLs belong to the site's verified domains.
   - Google Search Console URL inspection endpoint.
   - Public plain-text IndexNow key verification endpoint (`GET /api/v1/public/sites/<site_slug>/<key>.txt`).
6. **Multi-Tenant Security & IDOR Defense (TEN-3, SEC-3):**
   - Cross-tenant access to connections, keys, and submission logs returns HTTP 404 Not Found to prevent enumeration.

## Baseline (from Stage 04 commit `d2dc5d3`)

| Item | Finding |
|------|---------|
| Git commit | `d2dc5d3` ("Stage 4: SEO metadata, canonicals, safe JSON-LD, redirects, sitemap, robots, tests") |
| Services | PostgreSQL 16 on 55432, Redis 7 on 56379 running healthy in Docker Compose |
| Test suite | 81 tests passing |

## Files Created and Modified

### Common & Security (`apps/common`)
- `apps/common/crypto.py`: AES-256-GCM envelope encryption and decryption services (SEC-3).
- `tests/common/test_crypto.py`: Envelope encryption unit tests, tampering detection, and key mismatch handling.

### Integrations App (`apps/integrations`)
- `apps/integrations/apps.py`: Registered `IntegrationsConfig`.
- `apps/integrations/models.py`: `SearchEngineConnection`, `IndexNowKey`, and `IndexSubmissionLog`.
- `apps/integrations/adapters/base.py`: Abstract `BaseSearchEngineAdapter`.
- `apps/integrations/adapters/google.py`: `GoogleSearchConsoleAdapter` (sitemap submission & URL inspection).
- `apps/integrations/adapters/bing.py`: `BingWebmasterAdapter` (sitemap & SubmitUrlbatch).
- `apps/integrations/adapters/indexnow.py`: `IndexNowAdapter` (batch URL submission to IndexNow API).
- `apps/integrations/adapters/__init__.py`: Exported adapters package.
- `apps/integrations/tasks.py`: Celery tasks with exponential backoff, jitter, deduplication, and notification hooks.
- `apps/integrations/serializers.py`: DRF serializers with write-only credentials and immutable Meta fields.
- `apps/integrations/views.py`: Management views (`SearchConnectionListCreateView`, `SearchConnectionDetailView`, `IndexNowKeyView`, `IndexSubmissionLogListView`, `ManualSubmissionView`, `UrlInspectionView`) and public endpoint (`PublicIndexNowKeyFileView`).
- `apps/integrations/urls.py`: Management and public URL patterns.
- `apps/integrations/migrations/0001_initial.py`: Applied initial migrations.

### Core Configuration & Content Hooks
- `cms/celery.py`: Celery application setup with autodiscovery.
- `cms/__init__.py`: Exposed `celery_app`.
- `cms/settings/base.py`: Registered `apps.integrations` in `INSTALLED_APPS` and added `ENUM_NAME_OVERRIDES` in `SPECTACULAR_SETTINGS`.
- `cms/urls.py`: Mounted `apps.integrations.urls`.
- `apps/content/services.py`: Connected `transaction.on_commit` background search notification hook to `publish_article`.

### Test Suites
- `tests/integrations/test_adapters.py`: Mocked contract tests for Google, Bing, and IndexNow adapters.
- `tests/integrations/test_models.py`: Model unit tests, envelope encryption at rest, IndexNow key generation.
- `tests/integrations/test_jobs.py`: Celery job retry, backoff, deduplication window, and publish trigger tests.
- `tests/integrations/test_api.py`: Connection CRUD, credential isolation, manual submission domain validation, public key file delivery.
- `tests/security/test_idor.py`: Cross-tenant IDOR protection for integration endpoints.

## Requirements Verification Matrix

| Requirement | Implementation | Test Coverage | Status |
|-------------|----------------|---------------|--------|
| **SEC-3** (Encrypted Credentials) | AES-256-GCM envelope encryption with per-record DEKs under KEK | `tests/common/test_crypto.py`, `tests/integrations/test_models.py::test_search_connection_encryption_at_rest` | PASS |
| **OPS-1** (Search Engine Jobs) | Celery task with exponential backoff, jitter, retry limits, deduplication | `tests/integrations/test_jobs.py` (8 tests) | PASS |
| **INT-1** (Google Search Console) | Isolated adapter: Webmasters sitemap submission + URL Inspection API; disallows non-job Indexing API | `tests/integrations/test_adapters.py` (5 tests) | PASS |
| **INT-2** (Bing Webmaster Tools) | Isolated adapter: Sitemap submission + SubmitUrlbatch API | `tests/integrations/test_adapters.py` (4 tests) | PASS |
| **INT-3** (IndexNow Protocol) | Isolated adapter: Batch URL submission (up to 10k), 32-hex key generator, public key file delivery | `tests/integrations/test_adapters.py`, `tests/integrations/test_api.py::test_public_indexnow_key_file_delivery` | PASS |
| **TEN-3** (Anti-enumeration) | Cross-tenant access to connections, keys, and logs returns HTTP 404 | `tests/security/test_idor.py::test_cross_tenant_integrations_access_returns_404` | PASS |
| **SEC-1** (Decoupled CMS) | Zero imports from external MarketIntel modules; standalone architecture | `tests/test_no_marketintel_coupling.py::test_no_marketintel_internal_imports_in_source` | PASS |

## Test & Scan Results

### Test Execution & Code Coverage
```
collected 115 items
115 passed in 79.11s

Coverage: 85% total statement coverage (threshold >= 80%)
Model Coverage:
  - apps/accounts/models.py:     97%
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
  `ruff format --check .` -> 124 files already formatted.
- **Ruff Linter:**
  `ruff check .` -> All checks passed! 0 errors.
- **Mypy Static Typing:**
  `mypy apps` -> Success: no issues found in 68 source files.
- **Bandit Security Scanner:**
  `bandit -r apps -c pyproject.toml` -> Scanned 5,344 LOC, 0 issues identified.

## Independent Review & Security Review

1. **Credential Isolation & Write-Only Exposure (SEC-3):**
   - Verified that `SearchEngineConnectionSerializer` marks `credentials` as `write_only=True`. The raw secret is encrypted with AES-256-GCM before writing to the database column `encrypted_credentials`, and is never serialized back in any API response.
2. **Google Indexing API Policy Compliance:**
   - Evaluated `GoogleSearchConsoleAdapter`. Official Google guidelines explicitly restrict the Indexing API to `JobPosting` and `BroadcastEvent` structured data. The adapter prohibits standard article submission calls via this API, directing content indexing through XML sitemaps and URL inspection.
3. **IndexNow Host Ownership Verification:**
   - The public endpoint `GET /api/v1/public/sites/<site_slug>/<key>.txt` serves the 32-character key strictly in `text/plain; charset=utf-8` format when matching the site's generated key, satisfying Bing and Yandex crawler ownership verification.
4. **Idempotency & Rate-Limiting Protection (OPS-1):**
   - A 1-hour deduplication window based on SHA-256 hashes of `site:provider:article_id:hour` prevents redundant indexing submissions during rapid successive article revisions. Background tasks employ exponential backoff with randomized jitter on HTTP 429/5xx responses.

## Stage 05 Gate Decision

- **Gate Status:** `PASS`
- **Rationale:** All functional and security requirements for Stage 05 (Search engine adapters for Google, Bing, and IndexNow; AES-256-GCM envelope encryption at rest; resilient Celery publishing jobs with jittered backoff; public IndexNow verification file delivery; and cross-tenant IDOR defense) are fully implemented and verified by 115 passing tests at 85% total statement coverage (100% on integrations models) with zero warnings or errors across all static/security tools.
- **Next Stage:** Stage 06 — Analytics & Privacy-Preserving Event Ingestion (GA4 Reporting API integration, cookieless lightweight event collector, daily aggregation rollups, rate-limiting, and metric feeds).
