---
name: cms-backend-sde-workflow
description: Orchestrates a rigorous software-development-engineering workflow for a standalone, API-only headless CMS backend with multi-tenant content management, SEO, Google/Bing indexing integrations, GA4 reporting, cookie consent, privacy-preserving analytics, security reviews, and comprehensive testing. Use when planning, implementing, reviewing, testing, or hardening this CMS backend or a similar production API service.
---

# CMS Backend SDE Workflow

## Mission

Deliver a production-oriented, backend-only CMS service in small, reviewable stages. Every stage must be implemented, tested, independently reviewed, and validated against explicit acceptance criteria **before the next stage starts**. Prefer correct, secure, maintainable implementation over speed or large code-generation batches.

The service is initially standalone and must be designed for future integration into MarketIntel DB without depending on MarketIntel's internal code, database, models, or deployment. The frontend is out of scope; provide documented API contracts and integration instructions only.

## Non-negotiable rules

1. **Inspect before editing.** Inspect the workspace, existing files, Git status, dependency manifests, current architecture, tests, environment conventions, and deployment setup before changing code. Do not overwrite existing work or assume the repository is empty.
2. **Backend only.** Do not build React, Vue, Next.js, HTML admin pages, or a frontend consent banner. Build APIs, domain logic, jobs, schemas, integration adapters, documentation, and backend-serving endpoints only. Document what a future site-side SDK/component must do.
3. **No fake success.** Never claim an integration, external API call, test, migration, scan, or deployment passed unless it actually ran and its result was inspected. When credentials or a service are unavailable, distinguish a mocked test from a live verification and mark the latter blocked/unverified.
4. **Small vertical slices.** For each feature: define acceptance criteria → implement → test → inspect the diff → independent review → security review where relevant → run regression tests → record evidence → proceed only if the gate passes.
5. **Tests are part of the feature.** Do not defer all testing to the end. Add tests in the same stage as production code. Update tests whenever behavior changes.
6. **Do not weaken tests to get green.** Fix code or prove that a test is invalid. Do not skip, delete, loosen, or xfail a meaningful test without documenting a justified reason and an explicit blocker/approval.
7. **Protect tenant boundaries.** Every site/workspace-owned record and background job must be scoped to the authenticated tenant/site. Test cross-tenant access attempts for reads, writes, exports, and job status.
8. **Protect secrets.** Never commit real `.env` values, OAuth tokens, API keys, signing keys, cookies, or private site/repository contents into logs. Use environment variables or a secret manager and provide `.env.example` with placeholders only.
9. **No arbitrary code execution.** Never execute code retrieved from a customer's website or GitHub repository. Treat external HTML, repository contents, webhook payloads, metadata, and uploaded files as untrusted input.
10. **No unrelated scope.** Do not alter unrelated features or introduce dependencies that are not justified by requirements. Keep the service independently deployable.
11. **Current documentation matters.** When integrating external APIs, inspect official and current provider documentation. Confirm scopes, quotas, supported indexing mechanisms, token refresh, webhook rules, and API versions. Do not invent endpoint names or promise indexing/ranking.
12. **Be honest about external constraints.** Search engines decide whether and when to index pages. GA4 requires a site-side tag or integration to collect browser events. The backend alone cannot inject tags into a separate existing React application or infer real identities from anonymous cookies.

## SDE roles and responsibilities

Use actual parallel subagents when the environment supports them. Otherwise, perform each role sequentially as a distinct review pass; never claim an agent was spawned if it was not.

- **SDE Orchestrator / Tech Lead**: owns scope, stage order, dependency decisions, acceptance criteria, risk register, status, and stop/go gate.
- **Requirements Analyst / Product Engineer**: turns requirements into user stories, invariants, API behaviors, error cases, and measurable acceptance criteria. Calls out assumptions rather than silently inventing behavior.
- **Backend Architect**: owns modular boundaries, data model, transaction strategy, API versioning, integration interfaces, and standalone deployment architecture.
- **Backend Feature Engineer**: implements one approved vertical slice at a time, including migrations, serializers, services, permissions, jobs, and tests.
- **Integration Engineer**: implements provider adapters for Google Search Console, Bing Webmaster Tools, IndexNow, Google Analytics 4, and optional GitHub repository integration; uses official docs and provider mocks/contracts.
- **QA / Test Engineer**: independently tests acceptance criteria, negative cases, boundary cases, API contracts, regressions, migrations, and smoke-test flows.
- **Application Security Engineer**: reviews authentication, tenant isolation, OAuth, secrets, SSRF, URL/DNS validation, CORS, CSRF where applicable, injection, rate limits, abuse prevention, data retention, and privacy controls.
- **Independent Code Reviewer**: inspects the changed diff for correctness, readability, maintainability, race conditions, hidden coupling, backward compatibility, and tests. Must not rubber-stamp the implementer's claims.
- **DevOps / Reliability Engineer**: owns containerization, environment configuration, health/readiness checks, migrations, CI, logging, metrics, job retries, backups/runbooks, and deployment smoke tests.

## Required lifecycle for every stage

For each stage, follow this exact loop:

1. **Plan** — list scope, assumptions, files/modules likely affected, acceptance criteria, risks, and test commands.
2. **Implement** — make the smallest coherent change that satisfies the approved scope.
3. **Developer tests** — add and run unit/API/integration tests relevant to the change.
4. **Independent review** — review the full diff and public API changes; request fixes for defects.
5. **Security review** — mandatory for auth, tenant scoping, URLs/network calls, OAuth, tokens, cookies, analytics, uploads, webhooks, and external integrations.
6. **Regression validation** — run all applicable tests and static checks, including tests from prior stages.
7. **Evidence** — record commands, pass/fail counts, coverage, test doubles versus live provider checks, known issues, and files changed in `docs/engineering/stage-reports/`.
8. **Gate decision** — mark `PASS`, `BLOCKED`, or `FAIL` and give evidence. Only `PASS` permits the next stage. `BLOCKED` requires documenting missing credentials/environment and completing all local deterministic checks; do not represent blocked live checks as passed. `FAIL` means fix and rerun the current stage.

Do not combine multiple stages into one large unreviewed code-generation step. Do not start the next stage while a stage has unresolved critical/high findings, failing tests, unapplied migrations, broken OpenAPI, or undocumented acceptance gaps.

## Standard stage sequence

### Stage 0 — Workspace discovery and baseline
- Inspect repository structure, Git status, Python/runtime version, current dependencies, migrations, tests, CI, Docker, docs, `.env` handling, and current API conventions.
- Run the existing tests and checks before modifying anything; preserve baseline failures separately from new regressions.
- Produce `docs/engineering/requirements-matrix.md`, `architecture.md`, `threat-model.md`, `test-strategy.md`, and `risk-register.md`.
- Define out-of-scope items, especially all frontend work and direct coupling to MarketIntel DB.
- Gate: baseline documented; feature scope and acceptance criteria traceable; no unexamined destructive changes.

### Stage 1 — Architecture and foundations
- Select supported Python/Django/DRF versions based on current official compatibility, lock/pin dependencies, app structure, settings, environment validation, structured logging, API versioning, exception handling, OpenAPI, health/readiness endpoints, Docker, and CI.
- Use PostgreSQL for production and integration tests; do not rely solely on SQLite for behavior that depends on PostgreSQL constraints or JSON fields.
- Gate: clean install, configuration validation, migrations, `/health/live`, `/health/ready`, OpenAPI generation, and baseline CI succeed.

### Stage 2 — Identity, tenancy, and authorization
- Implement user/workspace/site membership and minimum required roles (owner/admin/editor/analyst or justified equivalent), password/session/token safety, refresh/expiry/revocation strategy, permissions, audit events, and tenant filters.
- Design an authentication adapter boundary so MarketIntel DB can later supply a trusted identity/token integration without importing its models now.
- Gate: positive and negative auth tests, ownership tests, role matrix, tenant isolation tests on every data-access pattern, and security review pass.

### Stage 3 — Sites, domains, and content lifecycle
- Implement site registration, normalized domain handling, domain ownership verification, content types/entries, schema validation, draft/published/archived lifecycle, slugs, history, and public published-only delivery APIs.
- Treat submitted URLs and DNS answers as hostile. Block private, loopback, link-local, and cloud metadata destinations for any server-side fetch; defend against DNS rebinding and redirects. Prefer DNS TXT verification and avoid fetching arbitrary URLs unless specifically required.
- Gate: CRUD, validation, publish/unpublish, duplicate-slug, domain verification, unauthorized access, tenant isolation, and public/private exposure tests pass.

### Stage 4 — SEO settings and rendering contracts
- Implement page SEO metadata, site defaults, canonical URL validation, robots directives, Open Graph/Twitter metadata, alt-text fields, safe structured-data JSON-LD handling, redirects with loop detection, sitemap generation inputs, and `robots.txt` configuration/API contracts.
- Distinguish storing settings from rendering them: document what the site-side adapter must emit in crawlable HTML and how static sites are regenerated/redeployed.
- Gate: canonical/indexability/redirect/sitemap tests, schema validation, output escaping, noindex/draft exclusion, and API contract review pass.

### Stage 5 — Search engine integrations and publishing jobs
- Add provider interfaces and isolated adapters for Google Search Console, Bing Webmaster Tools, and IndexNow. Verify current official documentation before implementing every endpoint and scope.
- Use OAuth state validation and PKCE where supported, least privilege, encrypted token storage, refresh handling, revocation, rate-aware retries, audit logs, idempotency, job deduplication, and per-site provider status.
- For Google: prioritize sitemap submission and Search Console/URL Inspection capabilities. Do not use Google's Indexing API for arbitrary pages; its supported use is restricted to specified page types. Do not claim successful indexing from accepted submission.
- For Bing/participating engines: support sitemap workflows and IndexNow URL notifications. Keep IndexNow key file/domain hosting requirements explicit in the integration instructions.
- Gate: adapter unit tests, provider contract tests with mocks, expiry/revocation/rate-limit/error tests, retry/idempotency tests, and live smoke check only if test credentials are explicitly configured.

### Stage 6 — Analytics and privacy-preserving visitor events
- Implement GA4 property/tag configuration and optional authorized report retrieval through official APIs. Keep site-side event collection separate from backend reporting access.
- If first-party event ingestion is included, accept only an allowlisted event schema; rate-limit and validate payloads; use opaque/pseudonymous visitor identifiers; do not fingerprint users; avoid retaining raw IP addresses or unnecessary user-agent detail; define retention and deletion policies.
- Clearly document that anonymous cookies cannot identify a person by name. Identity association only applies where the user voluntarily identifies themselves and processing is permitted.
- Gate: event validation, abuse/rate-limit tests, report authorization tests, token encryption, no-secret/no-PII logging checks, and retention/deletion tests pass.

### Stage 7 — Consent and cookie preference backend
- Implement per-site consent configuration, consent categories and policy versions, consent-record endpoints, timestamps, expiry/retention, export/deletion where required, and tag configuration contracts for a future browser integration.
- Do not implement a frontend banner. Document the exact API contract a future banner or SDK must use and how optional tags must remain blocked until consent is valid for the relevant jurisdiction/configuration.
- Integrate with Google Consent Mode only through supported documented configuration contracts; Consent Mode is not itself a consent banner or legal-compliance guarantee.
- Gate: consent defaults, accept/reject/customize, withdrawal, policy version change, expiry, tenant boundaries, and no tracking before allowed consent (at the integration-contract/test level) pass.

### Stage 8 — Optional GitHub repository integration
- Only implement if included in the approved scope. Prefer a GitHub App or least-privilege supported authorization. Let a customer explicitly select a repository and branch. Read code as untrusted data; never execute it.
- If generating integration changes, create a branch and pull request for review rather than pushing silently to a protected/default branch. Protect private content and tokens.
- Gate: OAuth/installation security, repository allowlist, path traversal/symlink handling, scope checks, tests for hostile repository content, and pull-request workflow tests pass.

### Stage 9 — Hardening and release readiness
- Run the full test suite, coverage, lint/format/type checks, dependency audit, SAST/security checks, secret scan, migration checks, production Django checks, OpenAPI validation, tenant isolation suite, and Docker smoke tests.
- Test empty database migration, upgrade migration from prior schema, rollback/recovery plan where feasible, health/readiness behavior, background worker startup, and external-provider outage behavior.
- Produce threat-model closure, operational runbook, deployment guide, backup/restore notes, integration guide, API reference, environment variable inventory, and release checklist.
- Gate: no unresolved critical/high defects, no unexplained failing tests, coverage target achieved or explicit justified exception documented, clean security scan or triaged findings, reproducible deployment, and all stage reports complete.

## Mandatory quality/test matrix

Run the checks applicable to the repository, adopting equivalent commands if tooling differs:

- **Unit tests:** domain services, serializers, validators, permissions, canonicalization, redirects, sitemap generation, consent decisions, token encryption, retry policy.
- **API tests:** success, malformed requests, missing fields, invalid types, pagination, filters, status codes, error schema, OpenAPI contract.
- **Database/integration tests:** real PostgreSQL, constraints, transaction rollback, migrations from clean and prior schema, uniqueness and concurrent publish/job behavior.
- **User/input validation:** all API payloads, slugs, domains, URLs, redirect targets, JSON-LD, event payloads, uploaded media metadata, OAuth callbacks, and provider IDs.
- **Authentication/authorization:** unauthenticated request, expired/revoked token, privilege escalation, role matrix, cross-tenant IDOR, public-versus-private content, admin-only actions.
- **Security:** OWASP API risks; SQL injection; XSS through stored metadata; SSRF and DNS rebinding; open redirects; CSRF/state validation; OAuth redirect URI validation; CORS misconfiguration; brute force and rate limiting; secrets in code/logs; insecure token storage; unsafe file/path handling; webhook authenticity; replay/idempotency.
- **Privacy:** no unnecessary PII, no raw secrets in logs, consent withdrawal, retention and deletion, tenant isolation, visitor pseudonym behavior, no fingerprinting, optional analytics gating contract.
- **External integrations:** mocked deterministic tests; contract tests; retry/timeout/backoff; 401/403/429/5xx; malformed responses; pagination; token expiry and refresh; live sandbox checks only when explicitly configured.
- **Smoke tests:** start API/database/worker/cache; apply migrations; verify readiness; create workspace/site; verify domain; create/publish content; fetch public content; fetch SEO metadata/sitemap; enqueue indexing notification; save/revoke integration; store/revoke consent; verify logs and no secret leakage.
- **Reliability/performance:** query count and N+1 checks on critical endpoints, pagination caps, rate-limited public endpoints, job deduplication, backpressure, provider outage simulation, basic load testing on the most-used APIs.
- **Release checks:** formatting/lint, types where configured, coverage, dependency audit, static security scan, secret scan, `manage.py check --deploy`, OpenAPI generation/validation, Docker build and smoke test.

Set a target of at least 80% overall statement coverage and 90% for security-sensitive modules (authentication, authorization, tenancy, OAuth/token handling, consent), unless the existing project has an established different target. Coverage numbers do not override missing critical test scenarios.

## Definition of done for every feature

A feature is not done until all items apply:

- Requirements and acceptance criteria are written and traceable to tests.
- Migration, API schema, authorization, validation, failure states, and logging are reviewed.
- Success and negative tests pass.
- Cross-tenant and unauthenticated behavior is tested where relevant.
- Independent code review findings are resolved or explicitly classified and approved.
- Security review is complete where applicable.
- Existing regression tests pass.
- Documentation and OpenAPI are updated.
- Stage report includes exact commands/results and remaining risks.
- No fake claims of live external verification.

## Required reporting format

At the end of each stage, summarize:

- Stage and scope
- Files/modules changed
- Acceptance criteria and evidence
- Commands run and actual result counts
- Coverage and static/security scan results
- External checks: `LIVE-PASS`, `MOCK-PASS`, or `BLOCKED`
- Review findings and remediation
- Remaining risks/blockers
- Gate: `PASS`, `BLOCKED`, or `FAIL`
- Next stage allowed: `YES` only when gate is `PASS`

Do not silently skip a stage. Do not finish by saying “all tests pass” without showing the commands and observed results. Finish the full engagement with a release-readiness summary and an honest inventory of anything not tested live.
