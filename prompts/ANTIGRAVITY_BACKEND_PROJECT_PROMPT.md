# Antigravity Project Prompt — Standalone Headless CMS Backend with SEO, Search Integrations, Analytics, Consent, and SDE Quality Gates

> **Use with the workspace skill:** `.agents/skills/cms-backend-sde-workflow/SKILL.md`  
> **Scope:** Backend only. Do not build a frontend/admin UI.  
> **Deployment goal:** Standalone service now; clean API integration into MarketIntel DB later.

## Your mission

Act as the SDE Orchestrator and build a production-oriented, standalone, API-only headless CMS backend. The service must let multiple customers register websites, manage structured content, configure technical SEO, request search-engine discovery/indexing actions through supported mechanisms, connect Google Analytics 4, and manage cookie-consent configuration and privacy-preserving visitor analytics.

Follow the skill `cms-backend-sde-workflow` throughout the task. Use distinct SDE roles (real subagents when available, otherwise separate sequential role-based passes). Every feature must be developed, tested, independently reviewed, security-reviewed where relevant, and validated against explicit acceptance criteria before proceeding. **Do not implement the whole system in one unreviewed pass.** A failing or blocked stage must stop progression until the gate rules are satisfied.

The backend must be independently deployable and must not import, query, mutate, or assume the internal models of MarketIntel DB. Provide versioned APIs, OpenAPI documentation, integration adapters, authentication boundaries, and documentation so MarketIntel DB can connect later through stable APIs.

## Mandatory first action: inspect and plan

1. Inspect the workspace, project files, Git status, Python/runtime versions, dependency manifests, existing tests, CI, container configuration, current environment conventions, and documentation before making changes.
2. If this workspace already contains code, preserve it and understand it. Do not overwrite unrelated work. If the workspace is empty, initialize a clean project.
3. Run existing tests/checks first and document baseline results, including any pre-existing failures.
4. Create these planning documents before core implementation:
   - `docs/engineering/requirements-matrix.md`
   - `docs/engineering/architecture.md`
   - `docs/engineering/threat-model.md`
   - `docs/engineering/test-strategy.md`
   - `docs/engineering/risk-register.md`
   - `docs/engineering/stage-reports/README.md`
5. Build an acceptance-criteria matrix linking each requirement to its module, endpoint, test, and stage gate.
6. Make reasonable implementation assumptions where needed, record them in the docs, and continue. Ask a question only when an essential requirement cannot be safely resolved from available information.

Do not begin Stage 1 until Stage 0 review and gate have passed.

## Product scope

### A. Standalone, multi-tenant foundation

Implement a multi-tenant API backend. Multiple customer workspaces can manage multiple sites, with strict tenant isolation across all records, API endpoints, background jobs, reports, integration connections, audit records, and exports.

Minimum domain model:

- `User`
- `Workspace` (tenant/customer account)
- `WorkspaceMembership` (role and membership state)
- `Site` (site key, display name, primary domain, normalized domains, framework, environment, status, owner workspace)
- `DomainVerification` (method, challenge/token, status, checked time, safe audit metadata)
- `ContentTypeDefinition` (key, label, schema/version, workspace/site scope as appropriate)
- `ContentEntry` (site/content type, slug, structured JSON data, locale if implemented, status, author, published version/timestamps)
- `ContentRevision` or equivalent version-history entity
- `PageSEO` (page/entry relation, title, meta description, canonical URL, index/follow directives, Open Graph/Twitter fields, robots overrides, safe structured-data configuration)
- `SiteSEOSettings` (defaults, organization/site information, sitemap settings, robots configuration, default social image)
- `RedirectRule` (source path, destination URL/path, status code, enabled state, audit owner; loop detection)
- `IntegrationConnection` and provider-specific records (provider, site, external IDs, scope/status, encrypted credentials reference, last verified/sync state)
- `IndexingJob` or durable provider-job representation (provider, URLs, idempotency key, attempts, next run, status, safe error category)
- `AnalyticsProperty` / `AnalyticsConnection` (GA4 property/stream/measurement identifiers, OAuth grant reference where required, consent/configuration status)
- `ConsentConfiguration` (categories, policy/version, default behavior, retention configuration)
- `ConsentRecord` (pseudonymous visitor ID, selected categories, policy version, timestamp, expiry/withdrawal state; avoid unnecessary PII)
- `AnalyticsEvent` (strict allowlisted event name, site, timestamp, pseudonymous visitor/session IDs if configured, allowlisted properties, consent basis/status, retention/delete status)
- `AuditEvent` (actor, workspace, site, action, target, timestamp, safe metadata; never secrets)

Adapt the exact model split based on a documented schema review. Use UUID identifiers where helpful for public/non-sequential identifiers. Enforce tenant/site ownership at the database/service/queryset/permission layer; do not rely only on frontend-supplied IDs or obscure UUIDs.

Minimum roles (adjust only with a written rationale):

- `OWNER`: full workspace/site management, member/connection ownership.
- `ADMIN`: manage sites, content, SEO, integration configuration, and permitted members.
- `EDITOR`: create/edit/publish content and SEO according to workspace policy; cannot manage credentials or members by default.
- `ANALYST`: read permitted analytics and SEO reports only; cannot change content or credentials.

Include an inactive/disabled account state and site/workspace suspension behavior. Registration should not be an unprotected open endpoint. Provide a safe initial-superuser/bootstrap process and configurable registration/invitation policy.

### B. Technology and architecture defaults

Use these defaults unless inspection shows the repository already uses a compatible convention:

- Python supported release selected from current official compatibility information.
- Django + Django REST Framework.
- PostgreSQL as the production database and the primary database used in integration tests.
- Celery + Redis (or a clearly justified durable equivalent) for provider API calls, sitemap refresh work, webhook handling, retries, and scheduled syncs. Do not perform slow external provider calls inside ordinary user-facing request handlers.
- `drf-spectacular` or an equivalent maintained library for OpenAPI 3 documentation.
- A maintained JWT/authentication approach suitable for first-party API auth, with short-lived access tokens, refresh rotation/revocation strategy as supported, and secure storage expectations documented. Use provider OAuth for Google/GitHub integrations separately; do not conflate user login with provider authorization.
- Django filters/pagination/throttling and structured validation/error handling.
- `pytest`, `pytest-django`, API client tests, factories, and appropriate HTTP mocks/provider contract tests.
- Ruff for lint/format and type checking where practical; Bandit or equivalent SAST, dependency audit, secret scan, and Django production checks.
- Docker and Docker Compose for API, worker, PostgreSQL, and Redis, plus CI that runs tests and static/security checks.

Use modular Django apps with clear boundaries, for example: `accounts`, `tenancy`, `sites`, `content`, `seo`, `search_integrations`, `analytics`, `consent`, `audit`, `github_integration` (only if included), and `common`. Avoid circular imports and overly broad “utils” modules. Use service functions for domain operations; keep views thin. Use transactions and idempotency for publish/revision/indexing workflows.

External provider calls must be behind provider interfaces/adapters. Tests must be able to replace adapters with deterministic fakes. Pin dependencies and record why each important dependency is used. Do not add unnecessary packages.

### C. Content management APIs

Implement a schema-driven content API suitable for headless websites. Support common content types such as pages, services, articles/blog posts, testimonials, and custom JSON-schema-like content types. Avoid hardcoding only one company's content model.

Required behavior:

- Create/edit/archive content types and entries within an authorized workspace/site.
- Validate payloads against the content type schema; reject unsupported fields and unsafe schema definitions.
- Draft, publish, unpublish, and archive lifecycle.
- Slug normalization, uniqueness per site/type/locale (if locale is implemented), and explicit conflict responses.
- Revision history and audit trail for content updates/publishing.
- Public delivery endpoints return only published and publicly allowed content.
- Private drafts and unpublished revisions must never be exposed through public API, sitemap, indexing notifications, analytics, or error messages.
- Pagination, filtering, ordering allowlists, response schema stability, and bounded query limits.
- Document cache/revalidation hooks for site-side integrations. Do not claim that cache purge occurs unless it is implemented and verified.

Required example endpoint families (final paths may change if the API spec documents them):

- `/api/v1/auth/…`
- `/api/v1/workspaces/…`
- `/api/v1/sites/…`
- `/api/v1/sites/{site_id}/content-types/…`
- `/api/v1/sites/{site_id}/entries/…`
- `/api/v1/public/sites/{public_site_key}/content/…`
- `/api/v1/public/sites/{public_site_key}/pages/{slug}`
- `/api/v1/audit-events/…`

Public delivery must use a site-scoped public identifier or signed/configured delivery mechanism, enforce allowed domain/origin behavior as a defense-in-depth measure, throttle abuse, and return only published data. CORS is not authentication and must never be treated as such. Do not expose private integration tokens in public delivery API responses.

### D. Domain and website connection workflow

Users must be able to create a site record by entering a URL/domain and selecting a framework (React/Vite, Next.js, WordPress, static/custom, or other supported value). Do not tell the user that entering a URL alone automatically connects a site or exposes its source code.

Implement:

- URL/domain normalization and validation.
- Ownership verification, preferably DNS TXT challenge with secure token generation, expiry, rate limits, and re-verification. If another verification method is added, explain its trust assumptions.
- Site integration state machine such as `created → domain_pending → verified → integration_pending → connected → error/suspended` as appropriate.
- A backend-generated integration guide and documented configuration/API contracts for supported frontend stacks. Because the frontend is explicitly out of scope, do not build browser UI or modify an external live website from this backend alone.
- Framework-neutral content and SEO API contracts plus adapter documentation describing how an external React/Vite or Next.js site renders data and metadata, handles revalidation, consumes consent configuration, and sends analytics events.
- Implement GitHub repository integration as the automated onboarding path: let a site owner authorize the CMS, select an authorized repository and branch, and disconnect/revoke access. Prefer a GitHub App with minimum repository permissions. Read source files as untrusted data, detect supported frameworks from manifests/configuration (initially React/Vite and Next.js), and generate a proposed integration branch/pull request for human review. Do not silently push to a protected/default branch, merge a PR, or deploy customer code. Never execute code from the repository. If a repository/framework cannot be safely handled, return a clear unsupported/manual-integration state and provide the documented integration guide. Keep the flow feature-flagged until provider credentials and security checks are configured.

Server-side URL/DNS operations are a security boundary. Block loopback, private, link-local, multicast, reserved and cloud-metadata destinations, validate every resolved address and redirect hop, defend against DNS rebinding, set short timeouts/response caps, and avoid fetching arbitrary full website URLs when DNS verification suffices. Do not SSRF-scan a user's URL as a shortcut to “connect” the site.

### E. SEO management and site technical SEO

Implement per-page and site-level SEO settings:

- SEO title and meta description.
- Canonical URL, with site/domain/path validation.
- Index/follow directives and a safe representation for robots directives.
- Open Graph and Twitter card fields, image references, alternative text for content images.
- Structured-data / JSON-LD configuration with schema validation, size limits, output escaping, and no fabricated ratings/reviews.
- Sitemap settings and eligibility rules.
- `robots.txt` configuration/preview API, including safe handling of disallow rules.
- Redirect rules (301/302 or supported safe redirect statuses) with path normalization, same-site policy, open-redirect protection, loop and chain detection, and tests.
- Defaults/inheritance from site SEO settings; page-specific overrides.
- SEO audit endpoint returning actionable diagnostics, severity, location/field, and remediation hints (missing/duplicate title, description, canonical mismatch, noindex conflict, missing image alt text, invalid schema, sitemap omission, broken internal link if a crawler is implemented, redirect chains, etc.). Make clear that audit scores are guidance and do not predict rankings.
- Publication events update sitemap output and enqueue eligible URL notifications. Do not include drafts, noindex pages, invalid canonical pages, or excluded/private paths in sitemaps or URL submission queues.

The backend stores and supplies settings, but the connected website must render them in its actual HTML/head. Document framework-specific rendering requirements. For Vite single-page applications, state clearly that crawlable SEO may require prerendering/server rendering; changing the CMS database alone does not modify static deployed HTML. For static builds, expose a revalidation/rebuild hook contract and do not claim deployed pages changed until the build/deploy system has acted.

### F. Google Search Console, Bing Webmaster Tools, and IndexNow

Create provider adapters and per-site connection state for:

**Google Search Console**
- OAuth authorization with supported least-privilege scopes, state validation, redirect URI allowlist, token expiry/refresh/revocation, encrypted-at-rest token storage, and audit trail.
- Verify/select an authorized Search Console property where supported; submit sitemap; check/report supported URL Inspection status where authorized and available.
- Queue work asynchronously; handle 401/403/429/5xx, quotas, pagination, bounded retries, exponential backoff with jitter, idempotency, and dead-letter/failed-job visibility.
- Never use the Google Indexing API for ordinary pages. Its supported use is restricted to specified job-posting/livestream page types. Use sitemap/Search Console workflows for general web pages.
- Distinguish `request_accepted` or `sitemap_submitted` from `indexed`. Never claim Google indexed a URL merely because a request was accepted.

**Bing Webmaster Tools**
- Support property/site association and sitemap workflows using the currently documented API/authorization method; store provider credentials securely.
- Return provider errors safely without exposing secrets.

**IndexNow**
- Generate a per-site key according to IndexNow requirements and document the customer-site key-file/hosting requirement.
- On eligible publish/update/delete, send URL notifications to the documented IndexNow endpoint or an explicitly configured participating endpoint.
- Batch, deduplicate, rate-limit, retry, and log safe outcomes. Do not imply that IndexNow submission guarantees indexing, and do not present it as Google indexing support.

Expose API endpoints for starting/confirming connections, viewing status, listing indexing jobs, submitting/retrying eligible URL notifications, and reading sync results. Keep all provider tokens server-side; public APIs may expose only non-secret integration status/configuration.

Verify all endpoints/scopes/quotas against official provider docs during implementation. Add sources/verification date in `docs/integrations/provider-notes.md`. Use deterministic provider mocks for tests; live checks require explicitly supplied credentials and must be reported separately.

### G. Google Analytics 4 integration and reporting

Implement two distinct parts:

1. **Site-side tagging configuration:** store a GA4 Measurement ID or supported Google Tag Manager configuration and return only the public configuration needed by the future site-side integration. Do not place OAuth refresh/access tokens or client secrets in this config.
2. **Authorized reporting:** optional Google OAuth connection allowing the customer to authorize read access to the relevant GA4 property and use the supported GA4 Data API for reports. Use least-privilege scopes and property authorization; a Measurement ID alone does not grant report access.

Required capabilities:

- Secure OAuth state, redirect allowlists, token refresh/revocation, encrypted token storage, connection status, scope records, and explicit disconnect.
- Reports for users/visitors as reported by GA4, sessions, views, source/medium, landing pages, engagement, and conversions where supported and authorized.
- Filter by site/property, date range limits, pagination/quotas, cached snapshots when suitable, safe API error handling, and job status for slow data retrieval.
- Document event definitions and the site-side tag/SDK contract for page views and opt-in custom events. The backend cannot collect browser events without a website-side tag or integration.
- Never describe GA4 anonymous/pseudonymous user statistics as verified real-world identity.

Do not build a frontend analytics dashboard; expose versioned API responses and API documentation only.

### H. Cookie consent and privacy-preserving first-party analytics

Build backend APIs and models; **do not build the frontend banner**. Define a clean contract for a future site-side consent manager/SDK.

Consent backend must support:

- Per-site consent policy/configuration and categories (essential/necessary, analytics, marketing; extendable without silently enabling new optional categories).
- Policy version, effective configuration, retention duration, jurisdiction/config flags if configured, and public consent configuration endpoint.
- Recording a visitor's consent choice, selected categories, policy version, timestamp, expiry, and withdrawal/change. Validate site, payload, category allowlist, and policy version.
- Anonymous/pseudonymous visitor identifier generated or managed by the site-side client; never use browser fingerprinting.
- Consent history export/deletion where applicable, retention jobs, and minimal audit records.
- A safe integration contract: optional analytics/marketing tags must not run until the necessary consent state exists, unless the site's documented lawful configuration explicitly provides another permitted basis. Consent Mode is not a banner or legal guarantee.

First-party event ingestion, if included:

- A public site-scoped endpoint for allowlisted events such as `page_view`, `cta_click`, `form_submit` with strict schema and property allowlists.
- Validate payload size, event names, timestamps, URL origin/site mapping, and rate limits; apply abuse mitigation.
- Do not accept arbitrary HTML, script code, arbitrary property keys, passwords, payment data, or unconstrained PII.
- Avoid storing raw IP addresses. If transient request IP information is needed for abuse controls, do not persist it in application event rows or routine logs. Avoid detailed user-agent retention unless justified and documented.
- Support configurable retention, deletion/anonymization, aggregation/report APIs, and tenant scoping.
- Ensure analytics events are accepted/processed according to the configured consent/policy contract; never circumvent consent controls or rely only on a hidden UI state.
- Document that cookies and pseudonymous IDs can help estimate sessions/return visits but do not by themselves disclose a person's real identity. Identity linkage is not part of the anonymous analytics feature.

This is a technical implementation, not a legal-compliance certification. Document data flows, retention, configurable consent behavior, and advise customers to review laws applicable to their audience and operations.

### I. Integration to MarketIntel DB later

The current codebase must remain standalone. Provide an integration contract rather than hard coupling.

- All APIs versioned under `/api/v1/` and described through OpenAPI.
- Configurable public base URL, CORS allowlist, trusted proxy settings, JWT issuer/audience validation strategy where applicable, and service-to-service authentication strategy.
- Define an authentication interface/adapter so a future MarketIntel DB token issuer can be integrated without changing domain logic. Do not accept arbitrary unsigned tokens or trust user IDs from request bodies.
- Use stable external identifiers and documented error formats. Define idempotency for mutating external integration operations.
- Provide `docs/integrations/marketintel-integration.md` with token trust assumptions, claim mapping, site/workspace mapping, permission mapping, API examples, retry rules, webhook/signature rules if applicable, and a phased integration plan.
- Do not add MarketIntel database credentials, schemas, app imports, or environment-specific names to core business logic.

### J. Observability and operations

Implement:

- Liveness and readiness endpoints (readiness verifies the required database and, where appropriate, queue availability without leaking internal details).
- Structured logs with request/correlation ID, tenant/site identifiers where safe, actor ID, operation, latency, and outcome; redact authorization headers, cookies, OAuth tokens, API keys, consent payload details, and sensitive analytics properties.
- Audit events for permission changes, domain verification, publishing, credential changes, OAuth connect/disconnect, indexing operations, consent policy changes, and data exports/deletions.
- Background-job status, retry policy, capped exponential backoff with jitter, idempotency keys, timeouts, and dead-letter/manual-retry controls.
- Environment validation at startup; safe placeholder `.env.example`; secrets manager integration points; secure headers/proxy configuration; database connection settings; backup/restore guidance; retention cleanup jobs.
- Docker Compose for local development and CI, production-oriented Dockerfile, migrations, and an operations/runbook document.

## Security requirements

Treat security as a release-blocking requirement, not a final optional pass.

- All object lookup must be authorized for tenant/site scope. Add explicit cross-tenant IDOR tests.
- Validate inputs using serializer/domain validation and DB constraints. Use ORM/parameterized queries; no string-built SQL.
- Apply rate limits to authentication, domain verification, public delivery, event ingestion, OAuth endpoints, indexing requests, and expensive reports.
- Enforce CORS via explicit configured origins; CORS is not authentication. Configure secure cookie/CSRF policy only where cookies are used by this API.
- Protect OAuth: validated state/PKCE where supported, exact redirect allowlists, minimal scopes, token encryption, refresh handling, revocation, and no tokens in URLs/logs.
- Validate DNS and external URLs against SSRF, private/reserved IPs, cloud metadata, redirect chains, DNS rebinding, response size, and timeouts.
- Protect webhook endpoints with provider signatures/secrets, timestamp/replay checks, and idempotency if webhooks are included.
- Prevent stored/reflected XSS in metadata/structured data through output-safe schemas and documented rendering contracts.
- Validate redirect destinations; prevent open redirects and loops.
- Defend against resource exhaustion: bounded payloads, pagination, query limits, job quotas, URL batch sizes, event quotas, connection timeouts.
- Run dependency vulnerability scans, SAST, secret scanning, Django deployment checks, and any available security tests. Triage findings; do not suppress findings just to pass CI.
- Apply data minimization, access controls, retention, and deletion to consent and analytics records.
- Do not log secrets, raw consent payloads, unnecessary PII, full third-party responses containing sensitive data, or private repository code.

## Required API and documentation output

Produce and maintain:

- OpenAPI JSON/YAML and interactive API docs in development.
- `README.md` with architecture, quick start, prerequisites, commands, local development, testing, and links to detailed docs.
- `.env.example` with placeholders and explanatory comments only.
- `docs/engineering/requirements-matrix.md` and stage reports.
- `docs/engineering/architecture.md`, `threat-model.md`, `test-strategy.md`, `risk-register.md`.
- `docs/api/auth-and-tenancy.md`, `content-api.md`, `seo-api.md`, `consent-and-analytics-api.md`, `integrations-api.md`, error format, pagination, rate limits, and API versioning policy.
- `docs/integrations/google-search-console.md`, `bing-webmaster.md`, `indexnow.md`, `google-analytics-4.md`, `site-framework-integration.md`, `marketintel-integration.md`, and `provider-notes.md` with official provider references and a review date.
- `docs/security/security-controls.md`, `privacy/data-flow-and-retention.md`, `docs/operations/deployment.md`, `runbook.md`, `backup-restore.md`, and `release-checklist.md`.
- CI workflow to install dependencies, check formatting/lint/types where set up, run tests and coverage, validate OpenAPI, run security/dependency scans, and build the container.

## Testing and user-validation requirements

Apply the SDE skill's mandatory stage gate for each stage. At minimum, implement and run:

1. Unit tests for validators, services, SEO rules, redirect safety, content lifecycle, consent rules, provider error mapping, token encryption, retry/idempotency behavior.
2. API tests for all endpoints including positive, unauthenticated, unauthorized, invalid input, not found, conflict, throttled, and provider-failure responses.
3. Authorization matrix tests for every role, every tenant-scoped object family, public/private content separation, and cross-tenant attacks.
4. PostgreSQL integration tests for constraints, transactions, concurrency-sensitive publishing and jobs, clean migrations, and upgrades from the previous migration.
5. OAuth and external integration tests for invalid state, wrong redirect, expired token, refresh failure, revocation, 401/403/429/5xx, timeouts, malformed provider response, and idempotent retry. Use mock provider tests by default and clearly identify them as mocks.
6. Privacy/consent tests for default state, accept/reject/customize, withdrawal, policy updates, expiry, retention cleanup, deletion/export, optional event gating contract, and lack of sensitive log leakage.
7. URL/SSRF tests for loopback/private/link-local/metadata IPs, IPv4/IPv6, domain normalization, DNS rebinding assumptions, redirects, malformed URLs, excessive responses, and timeout behavior.
8. SEO tests for metadata defaults, canonical URLs, noindex, Open Graph, JSON-LD validation, redirects and loops, sitemap inclusion/exclusion, robots output, unpublished/draft exclusion, and publication event creation.
9. Smoke test: start services, apply migrations, check liveness/readiness, bootstrap an admin, create workspace/site, verify domain, create/publish content, fetch public content, inspect SEO data/sitemap, enqueue indexing jobs, save an integration in mocked mode, save/revoke a consent record, and check logs for secrets.
10. Static and supply-chain checks: formatting, lint, type checks where configured, coverage, `manage.py check --deploy`, OpenAPI validation, dependency audit, SAST, secret scanning, container build and smoke test.
11. Basic performance/reliability tests for pagination caps, N+1 query regressions, public endpoint rate limits, job deduplication, provider outage behavior, and event ingestion quotas.

Target at least 80% overall statement coverage and 90% coverage for auth/permissions/tenant isolation/OAuth/consent modules unless the repository already specifies a different target. Coverage is not a substitute for testing the required security scenarios.

User validation means both API input validation and acceptance-criteria validation: create real request examples for normal and malicious inputs, confirm documented errors, and trace each requirement to passing tests. Do not claim “user validated” when no actual stakeholder reviewed it; label it “acceptance criteria validated by tests” where that is what happened.

## Stage plan and mandatory gates

Follow this exact order unless the Architect records a justified dependency change and the Orchestrator approves it. Complete the full SDE loop for each stage.

### Stage 0 — Discovery and requirements
- Inspect workspace and baseline.
- Write requirements matrix, architecture, threat model, test strategy, risk register, and stage-report framework.
- Review scope and acceptance criteria independently.
- **Gate:** baseline known; scope mapped; no implementation begins with unresolved critical assumptions.

### Stage 1 — Project foundation
- App skeleton, environment settings, structured logging, API versioning, exception format, OpenAPI, health/readiness, PostgreSQL, Redis/Celery, Docker/CI.
- **Gate:** clean install, migration, basic API tests, smoke startup, OpenAPI generation and CI pass.

### Stage 2 — Authentication, tenancy, and audit
- Identity, workspaces, memberships, roles, permission classes, audit events, auth adapter boundary.
- **Gate:** authorization matrix, negative auth, cross-tenant access tests and security review pass.

### Stage 3 — Site/domain lifecycle and content APIs
- Site onboarding, DNS TXT verification, schema-driven content, revisions, publishing, public delivery.
- **Gate:** complete CRUD/publish tests, SSRF/domain tests, published-only tests and tenant isolation pass.

### Stage 4 — SEO engine
- Page/site SEO settings, canonical validation, social metadata, structured data validation, redirects, sitemap/robots APIs and SEO audit.
- **Gate:** SEO requirement matrix and edge-case test suite pass; site-side rendering contracts documented.

### Stage 5 — Search provider integrations
- Provider abstractions; Google Search Console, Bing Webmaster Tools, IndexNow connection/workflow and asynchronous jobs.
- **Gate:** provider mocks/contracts, OAuth/security tests, retries/idempotency/rate handling, and docs pass. Any unavailable live credentials are marked `BLOCKED` rather than faked.

### Stage 6 — Analytics
- GA4 configuration and optional authorized reporting, first-party allowlisted event ingestion if included, reports and data retention.
- **Gate:** authorization, quota, PII/logging, event abuse, retention and provider error tests pass.

### Stage 7 — Consent backend
- Consent configuration/records, privacy policy versions, withdrawal, retention and browser integration API contract.
- **Gate:** consent lifecycle, tenant boundaries, retention/deletion and no-optional-tracking-before-consent contract tests pass.

### Stage 8 — GitHub repository onboarding and integration PRs
- Implement the authorized repository connection, repository/branch selection, supported-framework detection, source-as-untrusted-data analysis, integration patch generation for supported frameworks, and human-reviewed branch/PR flow. No repository code execution and no silent direct write/merge/deploy. Keep the integration feature-flagged until configured.
- **Gate:** OAuth/App permissions, tenant isolation, installation removal/revocation, malicious repository/path/symlink handling, secret redaction, patch safety, no default-branch writes, and mocked GitHub API tests pass. If live credentials are unavailable, mark live verification `BLOCKED` while maintaining passing deterministic mock tests.

### Stage 9 — Comprehensive QA and production readiness
- Run full test suite, regression matrix, migrations, static/security scans, Docker smoke, docs review, operations review, and release checklist.
- Resolve findings and rerun failing checks. Make a final release report separating live provider tests from mocked tests.
- **Gate:** no unresolved critical/high findings; all applicable tests and scans pass or have explicit documented blockers/approved exceptions; deployment steps reproducible.

## Progress reporting protocol

After every stage, create `docs/engineering/stage-reports/stage-XX.md` containing scope, files changed, acceptance criteria, commands and actual output summaries, pass/fail counts, coverage, lint/security scan results, external checks marked `LIVE-PASS`, `MOCK-PASS`, or `BLOCKED`, reviewer findings, fixes, residual risks, and the gate decision.

During execution, keep progress updates concise and evidence-based. If a long task is in progress, report completed durable findings between stages. Never say the task is complete while there are unresolved blockers or tests that have not run.

## Final release acceptance checklist

Do not mark the project complete until all applicable items are verified:

- [ ] Standalone backend runs from documented commands.
- [ ] No frontend/admin UI was added.
- [ ] No MarketIntel DB internal dependency exists.
- [ ] PostgreSQL migrations work from clean database and upgrade path.
- [ ] Auth, roles, workspace/site isolation, and audit logs are tested.
- [ ] Content draft/publish APIs validate data and expose only public published content.
- [ ] SEO metadata, canonical rules, redirects, sitemap, robots, structured data, and audit tests pass.
- [ ] GitHub repository onboarding, supported-framework detection, and human-reviewed integration PR generation are tested; no customer code is executed or silently deployed.
- [ ] Google Search Console, Bing, IndexNow and GA4 integration contracts are accurate and appropriately mocked/live-tested.
- [ ] Google Indexing API is not misused for general URLs.
- [ ] OAuth secrets are encrypted/stored safely and excluded from logs/responses.
- [ ] Consent API supports policy versions, choice recording, withdrawal, retention and deletion.
- [ ] Analytics is privacy-conscious, allowlisted, rate-limited and not represented as real-world identity.
- [ ] SSRF, IDOR, role bypass, validation, injection, redirect, rate-limit, and secret-leakage tests are covered.
- [ ] Unit/API/integration/smoke/regression tests run and actual results are reported.
- [ ] Lint/type/dependency/SAST/secret/OpenAPI/production checks are run and findings triaged.
- [ ] CI, Docker, `.env.example`, operations runbook, backup/restore and deployment docs are present.
- [ ] MarketIntel integration guide and stable versioned API/OpenAPI are present.
- [ ] Every stage has an independent review and gate report.

## Start now

Start at Stage 0 and follow the SDE skill. Inspect the actual workspace before edits. Do not start a later stage until the current stage has a documented `PASS` gate. Implement the complete backend in the stage order above, keep the frontend out of scope, and end with an evidence-based release-readiness report plus explicit live-integration blockers.
