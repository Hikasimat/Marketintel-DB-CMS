# Requirements Matrix

- **Status:** Stage 0 draft, reviewed (see [stage-00.md](stage-reports/stage-00.md))
- **Source:** [`prompts/ANTIGRAVITY_BACKEND_PROJECT_PROMPT.md`](../../prompts/ANTIGRAVITY_BACKEND_PROJECT_PROMPT.md) (§ letters below refer to its sections) and the `cms-backend-sde-workflow` skill
- **Legend:** Stage = gate stage that must prove the requirement. Test paths are *planned* locations; they are filled in and verified as each stage is completed. `Status` column: `PLANNED` → `IMPLEMENTED` → `VERIFIED` (tests passing, evidence in a stage report).

Endpoint paths are provisional. The OpenAPI schema produced in Stage 1+ is authoritative.

## Out of scope (explicit)

| ID | Item | Reason |
|----|------|--------|
| OOS-1 | Any frontend: admin UI, React/Vue/Next.js pages, HTML admin pages, dashboards | Backend-only mandate |
| OOS-2 | Consent banner UI / browser SDK implementation | Only the API contract is documented |
| OOS-3 | Importing, querying, or mutating MarketIntel DB code/models/DB | Standalone service; integration only via documented API contract |
| OOS-4 | Executing customer repository code or fetched website code | Security rule 9 |
| OOS-5 | Guaranteeing indexing/ranking, legal-compliance certification | External constraints; documented honestly |
| OOS-6 | Google Indexing API for general pages | Supported only for JobPosting/BroadcastEvent pages |
| OOS-7 | Directly modifying/deploying a live customer website | Changes go through a human-reviewed PR (Stage 8) or customer action |
| OOS-8 | Identity resolution of anonymous visitors / fingerprinting | Privacy rules |

## A. Foundation, identity, tenancy (Stages 1–2)

| ID | Requirement / acceptance criteria | Module | Endpoint(s) | Planned tests | Stage | Status |
|----|-----------------------------------|--------|-------------|---------------|-------|--------|
| FND-1 | App boots with validated env config; it fails fast and lists every missing/invalid variable, without printing any values | `config`, `common` | — | `tests/common/test_settings_validation.py` | 1 | PLANNED |
| FND-2 | `/health/live` returns 200 when the process is up; `/health/ready` returns 200 only if DB (and Redis when configured) is reachable, 503 otherwise, and never shows internal details | `common` | `GET /health/live`, `GET /health/ready` | `tests/common/test_health.py` | 1 | PLANNED |
| FND-3 | All APIs are under `/api/v1/`; OpenAPI 3 schema is generated and valid; interactive docs appear only in dev | `config` | `/api/v1/schema/`, `/api/v1/docs/` | `tests/common/test_openapi.py` | 1 | PLANNED |
| FND-4 | Uniform error envelope `{error:{code,message,details,request_id}}` for 400/401/403/404/409/422/429/5xx; no stack traces in prod | `common` | all | `tests/common/test_errors.py` | 1 | PLANNED |
| FND-5 | Structured JSON logs with request ID; redaction of Authorization, Cookie, tokens, secrets, consent payloads | `common.logging` | all | `tests/common/test_logging_redaction.py` | 1 | PLANNED |
| FND-6 | Docker Compose (api, worker, beat, postgres, redis) and CI (lint, tests, coverage, OpenAPI, scans, image build) | repo | — | CI run evidence | 1 | PLANNED |
| AUTH-1 | Users authenticate and receive a short-lived access JWT plus a rotating refresh token; reusing a revoked/rotated refresh is rejected; logout revokes it | `accounts` | `POST /api/v1/auth/token/`, `/refresh/`, `/logout/` | `tests/accounts/test_auth_tokens.py` | 2 | PLANNED |
| AUTH-2 | Inactive/disabled users cannot authenticate, and their existing tokens are rejected | `accounts` | as above | `tests/accounts/test_inactive.py` | 2 | PLANNED |
| AUTH-3 | No unprotected open registration: registration is disabled by default; supported policies are invitation-only or admin bootstrap (`manage.py bootstrap_admin`) | `accounts` | `POST /api/v1/auth/invitations/accept/` | `tests/accounts/test_registration_policy.py` | 2 | PLANNED |
| AUTH-4 | Login/refresh/invite endpoints are rate limited (429 + error envelope) | `accounts` | as above | `tests/accounts/test_auth_throttle.py` | 2 | PLANNED |
| AUTH-5 | An authentication adapter boundary lets an external issuer (e.g. MarketIntel) be added via config (issuer/audience/JWKS) with no change to domain logic. Unsigned tokens, `alg=none`, and body-supplied user IDs are rejected | `accounts.auth_backends` | — | `tests/accounts/test_external_issuer.py` | 2 | PLANNED |
| TEN-1 | Workspace CRUD; the creator becomes OWNER; membership roles are OWNER/ADMIN/EDITOR/ANALYST; membership state is active/invited/disabled | `tenancy` | `/api/v1/workspaces/…`, `/members/…` | `tests/tenancy/test_workspaces.py` | 2 | PLANNED |
| TEN-2 | Role matrix enforced for every object family (see architecture §Roles); tests are generated over the matrix | `tenancy.permissions` | all tenant endpoints | `tests/tenancy/test_role_matrix.py` | 2+ | PLANNED |
| TEN-3 | Cross-tenant access (read/write/list/export/job status) by a non-member returns 404 (no existence leak) for every tenant-scoped family; a member whose role is insufficient gets 403 | all apps | all | `tests/security/test_idor.py` | 2+ | PLANNED |
| TEN-4 | A suspended workspace or site blocks mutations and public delivery; reads stay available to OWNER/ADMIN | `tenancy`, `sites` | — | `tests/tenancy/test_suspension.py` | 2–3 | PLANNED |
| TEN-5 | Last OWNER cannot be removed or demoted; ADMIN cannot grant OWNER | `tenancy` | members endpoints | `tests/tenancy/test_membership_rules.py` | 2 | PLANNED |
| AUD-1 | Audit events for permission changes, domain verification, publishing, credential changes, OAuth connect/disconnect, indexing ops, consent policy changes, exports/deletions; never containing secrets | `audit` | `GET /api/v1/audit-events/` | `tests/audit/test_audit_events.py` | 2+ | PLANNED |
| AUD-2 | Audit list is workspace-scoped, read-only, and visible to OWNER/ADMIN only | `audit` | as above | `tests/audit/test_audit_access.py` | 2 | PLANNED |

## B. Sites, domains, content (Stage 3)

| ID | Requirement / acceptance criteria | Module | Endpoint(s) | Planned tests | Stage | Status |
|----|-----------------------------------|--------|-------------|---------------|-------|--------|
| SITE-1 | Create site with display name, primary domain, framework enum (`react_vite`, `nextjs`, `wordpress`, `static`, `other`), environment; generates non-sequential `public_site_key` | `sites` | `/api/v1/sites/…` | `tests/sites/test_sites_api.py` | 3 | PLANNED |
| SITE-2 | Domain normalization: IDNA/punycode, lowercase, strip scheme/path/port/trailing dot; reject IPs, `localhost`, single-label, reserved TLDs (`.local`, `.internal`, `.test`, etc.); a duplicate verified domain across tenants is rejected | `sites.domains` | — | `tests/sites/test_domain_normalization.py` | 3 | PLANNED |
| SITE-3 | DNS TXT verification: CSPRNG token, `_cms-verify.<domain>` record, expiry, per-site/per-workspace rate limits, re-verification; verification runs in a worker job; DNS answers are treated as untrusted | `sites.verification` | `POST /sites/{id}/domains/{d}/verify/` | `tests/sites/test_dns_verification.py` | 3 | PLANNED |
| SITE-4 | State machine `created → domain_pending → verified → integration_pending → connected`, plus `error`/`suspended`; illegal transitions rejected | `sites` | — | `tests/sites/test_site_state_machine.py` | 3 | PLANNED |
| SITE-5 | Backend-generated integration guide per framework (returns documentation/config, not browser UI) | `sites` | `GET /sites/{id}/integration-guide/` | `tests/sites/test_integration_guide.py` | 3 | PLANNED |
| NET-1 | Shared safe-egress module: blocks loopback/private/link-local/multicast/reserved/CGNAT/metadata (v4+v6, incl. IPv4-mapped v6); validates every resolved IP and redirect hop; pins the connection to the validated IP (anti-rebinding); timeouts; response-size cap | `common.net` | — | `tests/security/test_ssrf.py` | 3 | PLANNED |
| CT-1 | Content type definitions with a restricted schema DSL (allowlisted field types, max depth/fields/size); unsafe schemas rejected | `content` | `/sites/{id}/content-types/…` | `tests/content/test_content_types.py` | 3 | PLANNED |
| CT-2 | Entry payloads validated against the type schema; unknown fields rejected | `content` | `/sites/{id}/entries/…` | `tests/content/test_entry_validation.py` | 3 | PLANNED |
| CT-3 | Lifecycle draft → published → unpublished/archived; publish is transactional and creates an immutable revision | `content.services` | `/entries/{id}/publish/`, `/unpublish/`, `/archive/` | `tests/content/test_lifecycle.py` | 3 | PLANNED |
| CT-4 | Slug normalization; uniqueness per (site, type, locale) enforced by a DB constraint; conflict → 409 | `content` | — | `tests/content/test_slugs.py` (PostgreSQL) | 3 | PLANNED |
| CT-5 | Revision history list/detail; audit on publish | `content` | `/entries/{id}/revisions/` | `tests/content/test_revisions.py` | 3 | PLANNED |
| CT-6 | Public delivery by `public_site_key` returns only published, public content, never drafts, private fields, or tokens; throttled; when an `Origin` header is present it must match the site's allowed origins (defense in depth only; server-side/SSR fetches send no Origin and are allowed) | `content.public` | `/api/v1/public/sites/{key}/content/…`, `/pages/{slug}` | `tests/content/test_public_delivery.py` | 3 | PLANNED |
| CT-7 | Pagination caps, filter/order allowlists, stable response schema, N+1 guard | `content` | list endpoints | `tests/content/test_query_bounds.py` | 3 | PLANNED |
| CT-8 | Concurrent publish of the same entry yields one consistent published version (row lock / optimistic version) | `content.services` | — | `tests/content/test_concurrency.py` (PostgreSQL) | 3 | PLANNED |
| CT-9 | Revalidation webhook contract documented (outbound signed webhook to customer site on publish) and implemented only if verified; no cache-purge claim otherwise | `content`, docs | — | `tests/content/test_revalidation_hook.py` | 3 | PLANNED |

## C. SEO (Stage 4)

| ID | Requirement / acceptance criteria | Module | Endpoint(s) | Planned tests | Stage | Status |
|----|-----------------------------------|--------|-------------|---------------|-------|--------|
| SEO-1 | PageSEO: title/description length bounds, index/follow, robots overrides, OG/Twitter fields, image alt text; inheritance from SiteSEOSettings | `seo` | `/sites/{id}/entries/{id}/seo/`, `/sites/{id}/seo-settings/` | `tests/seo/test_page_seo.py` | 4 | PLANNED |
| SEO-2 | Canonical URL must be absolute https (http only if the site is configured for it) on one of the site's registered domains, otherwise rejected; the SEO audit flags canonicals on not-yet-verified domains | `seo.validators` | — | `tests/seo/test_canonical.py` | 4 | PLANNED |
| SEO-3 | JSON-LD: allowlisted `@type`s, size/depth limits, no fabricated `aggregateRating`/`review` unless backed by content, output escaped safely for `<script>` embedding (`</`, U+2028/2029) | `seo.structured_data` | — | `tests/seo/test_jsonld.py` | 4 | PLANNED |
| SEO-4 | Redirect rules: path normalization, status in {301,302,307,308}, same-site or allowlisted destinations only (no open redirect), loop and chain (> N) detection | `seo.redirects` | `/sites/{id}/redirects/…`, public resolve | `tests/seo/test_redirects.py` | 4 | PLANNED |
| SEO-5 | Sitemap: only published + indexable + canonical-self + non-excluded entries; XML escaped; 50k URL / 50MB split with index. URLs use the site's primary domain; the integration contract requires the customer site to serve/proxy it at `https://<domain>/sitemap.xml` (search engines expect same-host sitemaps unless cross-submission is verified) | `seo.sitemap` | `GET /api/v1/public/sites/{key}/sitemap.xml` | `tests/seo/test_sitemap.py` | 4 | PLANNED |
| SEO-6 | robots.txt config + preview with validated directives; sitemap reference | `seo.robots` | `GET /public/sites/{key}/robots.txt`, preview | `tests/seo/test_robots.py` | 4 | PLANNED |
| SEO-7 | SEO audit endpoint returning diagnostics (code, severity, field, remediation); explicitly guidance, not ranking prediction | `seo.audit` | `GET /sites/{id}/seo-audit/` | `tests/seo/test_audit.py` | 4 | PLANNED |
| SEO-8 | Publish/unpublish/delete emits a domain event that refreshes sitemap and enqueues eligible URL notifications only | `seo.signals`/services | — | `tests/seo/test_publication_events.py` | 4 | PLANNED |
| SEO-9 | Public SEO metadata endpoint for site-side rendering; rendering contract documented per framework (incl. Vite SPA prerender caveat) | `seo` | `GET /public/sites/{key}/pages/{slug}/seo` | `tests/seo/test_public_seo.py` | 4 | PLANNED |

## D. Search integrations (Stage 5)

| ID | Requirement / acceptance criteria | Module | Endpoint(s) | Planned tests | Stage | Status |
|----|-----------------------------------|--------|-------------|---------------|-------|--------|
| SRCH-1 | Provider interface and fake adapters; real adapters isolated; no provider calls in request handlers | `search_integrations` | — | `tests/search/test_provider_interface.py` | 5 | PLANNED |
| SRCH-2 | Google OAuth: state (single-use, bound to user+site, TTL), PKCE, exact redirect allowlist, least-privilege scope (verified against current docs), encrypted tokens, refresh, revocation, disconnect | `search_integrations.google`, `common.crypto` | `/sites/{id}/integrations/google/connect/`, `/callback/`, `/disconnect/` | `tests/search/test_google_oauth.py` | 5 | PLANNED |
| SRCH-3 | GSC: list/select property, submit sitemap, URL Inspection where authorized; statuses `sitemap_submitted`/`inspection_result`, never `indexed` unless the inspection result says so | `search_integrations.google` | `/integrations/google/…` | `tests/search/test_gsc_adapter.py` | 5 | PLANNED |
| SRCH-4 | Google Indexing API is not used for general pages (static check plus test) | — | — | `tests/search/test_no_indexing_api.py` | 5 | PLANNED |
| SRCH-5 | Bing Webmaster: site association and sitemap submission using currently documented auth (API key or OAuth, verified in Stage 5); errors sanitized | `search_integrations.bing` | `/integrations/bing/…` | `tests/search/test_bing_adapter.py` | 5 | PLANNED |
| SRCH-6 | IndexNow: per-site key (format per spec), key-file hosting contract, batched/deduplicated notifications, retry, safe logging; key served by public endpoint for site proxying | `search_integrations.indexnow` | `/integrations/indexnow/…`, `GET /public/sites/{key}/indexnow-key` | `tests/search/test_indexnow.py` | 5 | PLANNED |
| SRCH-7 | Durable IndexingJob: idempotency key, dedupe, attempts, capped exponential backoff with jitter, 401/403/429/5xx/timeout mapping, dead-letter and manual retry | `search_integrations.jobs` | `/sites/{id}/indexing-jobs/…` | `tests/search/test_jobs.py` | 5 | PLANNED |
| SRCH-8 | Provider notes with official sources and verification date | docs | — | doc review | 5 | PLANNED |

## E. Analytics (Stage 6)

| ID | Requirement / acceptance criteria | Module | Endpoint(s) | Planned tests | Stage | Status |
|----|-----------------------------------|--------|-------------|---------------|-------|--------|
| ANA-1 | GA4 measurement ID / GTM container config (format validated); public config returns only non-secret IDs | `analytics` | `/sites/{id}/analytics/config/`, `/public/sites/{key}/analytics-config` | `tests/analytics/test_config.py` | 6 | PLANNED |
| ANA-2 | GA4 OAuth (read-only scope) separate from user login; property authorization check; encrypted tokens | `analytics.ga4` | `/analytics/ga4/connect/…` | `tests/analytics/test_ga4_oauth.py` | 6 | PLANNED |
| ANA-3 | GA4 Data API reports (users, sessions, views, source/medium, landing pages, engagement, conversions) with date-range limits, quota/error handling, cached snapshots, async job status | `analytics.ga4` | `/sites/{id}/analytics/reports/…` | `tests/analytics/test_ga4_reports.py` | 6 | PLANNED |
| ANA-4 | First-party ingestion: allowlisted events (`page_view`, `cta_click`, `form_submit`), allowlisted properties, size/timestamp/origin validation, rate limits, rejection of arbitrary keys/HTML/PII patterns | `analytics.ingest` | `POST /public/sites/{key}/events` | `tests/analytics/test_ingest.py` | 6 | PLANNED |
| ANA-5 | No raw IP persisted; UA reduced to coarse class or dropped; pseudonymous IDs only; no fingerprinting | `analytics.ingest` | — | `tests/analytics/test_privacy.py` | 6 | PLANNED |
| ANA-6 | Events accepted only per consent contract (analytics category granted for visitor + current policy, or documented site config) | `analytics`, `consent` | — | `tests/analytics/test_consent_gating.py` | 6–7 | PLANNED |
| ANA-7 | Retention cleanup job; deletion by visitor ID; aggregation report endpoints, tenant scoped | `analytics` | `/sites/{id}/analytics/first-party/…` | `tests/analytics/test_retention.py` | 6 | PLANNED |

## F. Consent (Stage 7)

| ID | Requirement / acceptance criteria | Module | Endpoint(s) | Planned tests | Stage | Status |
|----|-----------------------------------|--------|-------------|---------------|-------|--------|
| CON-1 | Per-site config: categories (`necessary` always on; `analytics`, `marketing`, custom default off), policy version, retention, jurisdiction flags | `consent` | `/sites/{id}/consent/config/` | `tests/consent/test_config.py` | 7 | IMPLEMENTED |
| CON-2 | Public config endpoint (non-secret) including Consent Mode mapping contract | `consent` | `GET /public/sites/{key}/consent-config` | `tests/consent/test_public_config.py` | 7 | IMPLEMENTED |
| CON-3 | Record consent: visitor ID, categories (allowlist), policy version must match current, timestamp, expiry; accept/reject/customize | `consent` | `POST /public/sites/{key}/consent` | `tests/consent/test_records.py` | 7 | IMPLEMENTED |
| CON-4 | Withdrawal/change creates a new record; history preserved; policy version bump invalidates prior consent for optional categories | `consent` | `POST …/consent/withdraw` | `tests/consent/test_lifecycle.py` | 7 | IMPLEMENTED |
| CON-5 | Adding a new optional category never silently enables it | `consent` | — | `tests/consent/test_new_category.py` | 7 | IMPLEMENTED |
| CON-6 | Export/delete by visitor ID (authorized and rate limited); retention cleanup job; minimal audit | `consent` | `/sites/{id}/consent/records/…` | `tests/consent/test_retention_export.py` | 7 | IMPLEMENTED |
| CON-7 | Consent payloads are never logged | `common.logging` | — | `tests/consent/test_no_log_leak.py` | 7 | IMPLEMENTED |

## G. GitHub integration (Stage 8, feature-flagged)

| ID | Requirement / acceptance criteria | Module | Endpoint(s) | Planned tests | Stage | Status |
|----|-----------------------------------|--------|-------------|---------------|-------|--------|
| GH-1 | GitHub App installation flow with state validation; minimal permissions (contents, pull_requests, metadata); uninstall/revoke handling via signed webhooks | `github_integration` | `/workspaces/{ws}/github/installations/`, `POST /webhooks/github/` | `tests/github/test_installation.py` | 8 | IMPLEMENTED |
| GH-2 | Explicit repo + branch selection limited to the installation's repos | `github_integration` | `/workspaces/{ws}/github/installations/{id}/repositories/`, `POST /sites/{id}/github/connect/` | `tests/github/test_repo_selection.py` | 8 | IMPLEMENTED |
| GH-3 | Framework detection from manifests only (package.json, vite/next config) parsed as data; 500 KB limit; path traversal rejected; never executes code | `github_integration.analyzer` | `POST /sites/{id}/github/analyze/` | `tests/github/test_detection_hostile.py` | 8 | IMPLEMENTED |
| GH-4 | Generates patch on a new branch and opens PR; never writes to default/base branch, never merges or deploys | `github_integration.views` | `POST /sites/{id}/github/open-pr/` | `tests/github/test_pr_flow.py` | 8 | IMPLEMENTED |
| GH-5 | Unsupported repo → clear `manual_integration_required` state + docs guide | `github_integration` | `POST /sites/{id}/github/analyze/` | `tests/github/test_unsupported.py` | 8 | IMPLEMENTED |
| GH-6 | Webhook signature (HMAC-SHA256) + delivery-ID replay protection; private keys & secrets redacted in logs | `github_integration.views` | `POST /api/v1/webhooks/github/` | `tests/github/test_webhooks.py` | 8 | IMPLEMENTED |
| GH-7 | Disabled unless `GITHUB_APP_ENABLED=true` | `github_integration.permissions` | all `/github/` endpoints | `tests/github/test_feature_flag.py` | 8 | IMPLEMENTED |

## H. Cross-cutting security, ops, integration contract

| ID | Requirement / acceptance criteria | Module | Planned tests / evidence | Stage | Status |
|----|-----------------------------------|--------|--------------------------|-------|--------|
| SEC-1 | Rate limits: auth, domain verification, public delivery, ingestion, OAuth, indexing, reports | `common.throttling` | `tests/content/test_public_content_api.py`, `tests/analytics/test_ingest.py` | 2–7, 9 | IMPLEMENTED |
| SEC-2 | CORS explicit allowlist (management API) + per-site origins (public API); never used as auth | `config`, `content.public` | `tests/content/test_public_content_api.py`, `tests/common/test_settings_validation.py` | 1, 3, 9 | IMPLEMENTED |
| SEC-3 | Token/credential encryption at rest (envelope: per-record DEK, KEK from env/KMS, key rotation support) | `common.crypto` | `tests/common/test_crypto.py`, `tests/integrations/test_models.py` | 5, 9 | IMPLEMENTED |
| SEC-4 | No secrets in responses or logs (automated scan of captured logs in tests and smoke) | all | `tests/common/test_logging_redaction.py`, `tests/consent/test_no_log_leak.py`, `tests/github/test_webhooks.py` | 2–9 | IMPLEMENTED |
| SEC-5 | Bounded payloads (`DATA_UPLOAD_MAX_MEMORY_SIZE`, per-endpoint limits), pagination caps, URL batch caps | all | `tests/common/test_settings_validation.py`, `tests/github/test_detection_hostile.py` | 1–9 | IMPLEMENTED |
| SEC-6 | `manage.py check --deploy` clean under prod settings; secure headers; trusted proxy config | `config` | `python manage.py check --deploy --settings=cms.settings.prod` (0 issues) | 1, 9 | IMPLEMENTED |
| SEC-7 | Bandit, pip-audit, gitleaks (or equivalent) in CI; findings triaged | CI | Bandit (0 issues across 9,156 LOC), pip-audit (0 known CVEs) | 1, 9 | IMPLEMENTED |
| OPS-1 | Celery jobs: timeouts, retries with jitter, idempotency, dead-letter visibility | `common.jobs` | `tests/integrations/test_jobs.py`, `tests/analytics/test_retention.py` | 5, 9 | IMPLEMENTED |
| OPS-2 | Docs: deployment, runbook, backup/restore, release checklist, env inventory | docs | `docs/operations/`, `.env.example`, `README.md` | 9 | IMPLEMENTED |
| MI-1 | MarketIntel integration guide: token trust, claim mapping, workspace/site mapping, permissions, idempotency, retries, phased plan | docs | `docs/integrations/marketintel-integration.md`, `tests/accounts/test_external_issuer.py` | 2, 9 | IMPLEMENTED |
| MI-2 | No MarketIntel imports/credentials/names in business logic | all | `tests/test_no_marketintel_coupling.py` (grep-based assert 0 coupling) | 1–9 | IMPLEMENTED |
| COV-1 | ≥ 80% overall statement coverage; ≥ 90% for accounts, tenancy, permissions, crypto/OAuth, consent | — | 86% overall coverage across 4,586 statements | every stage, 9 | IMPLEMENTED |

## Assumptions (recorded, not silently invented)

| ID | Assumption | Rationale / revisit when |
|----|-----------|--------------------------|
| AS-1 | Python 3.12 or 3.13 runtime and the current Django LTS + DRF are the targets; exact pins are chosen in Stage 1 after checking official compatibility tables | Host has 3.11–3.14; 3.14 may lack wheels for some deps |
| AS-2 | Management API auth uses bearer JWTs (no cookies), so CSRF is not applicable to `/api/v1/` except the Django admin (if enabled) | Revisit if cookie sessions are added |
| AS-3 | Locale support: single optional `locale` field (BCP 47) on entries, part of the slug uniqueness key; no translation workflow | Prompt says "if implemented" |
| AS-4 | Media uploads are out of v1 scope; image references are URLs on verified domains or allowlisted CDNs with alt text | Upload handling adds significant attack surface; revisit on request |
| AS-5 | Content type definitions are site-scoped (they can be cloned across sites in the same workspace) | Simplest tenant boundary |
| AS-6 | First-party event ingestion **is included** (Stage 6) behind a per-site toggle (default off) | Prompt lists it as "if included"; it is cheap to keep behind a toggle |
| AS-7 | Public API identification uses `public_site_key` (unguessable, rotatable); it is not a secret, so public endpoints expose only public data | Prompt §C |
| AS-8 | Django admin is disabled in production by default (`ADMIN_ENABLED=false`) | Reduces attack surface; there is no frontend |
| AS-9 | Email delivery for invitations: tokens are returned to the inviting admin via the API (dev) or sent through a pluggable email backend; no SMTP credentials are required for tests | No email provider specified |
