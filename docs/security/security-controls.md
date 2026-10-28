# Security Controls & Threat Model Closure

## 1. Overview & Threat Model Closure

This document presents the technical security controls implemented across the CMS Backend and records the closure of threats identified during initial architecture modeling ([`docs/engineering/threat-model.md`](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/engineering/threat-model.md)).

| Threat ID | Threat Description | Mitigation & Architectural Control | Invariant / Status |
|-----------|--------------------|-------------------------------------|---------------------|
| **T-1: Cross-Tenant IDOR & Enumeration** | Attacker accesses or enumerates resources belonging to another tenant workspace. | All database lookups are strictly scoped via `resolve_workspace`. Unmatched or cross-tenant requests return `HTTP 404 Not Found` (TEN-3 anti-enumeration), verified in `tests/security/test_idor.py`. | **CLOSED** |
| **T-2: Token Compromise & Replay** | Stolen refresh token used to generate unauthorized access tokens. | Cryptographic token rotation with token family tracking. Reusing a rotated refresh token triggers instantaneous revocation of the entire token family (`apps/accounts/tokens.py`), verified in `tests/accounts/test_token_rotation.py`. | **CLOSED** |
| **T-3: SSRF via Domain Verification & Webhooks** | Attacker specifies internal IPs (AWS metadata `169.254.169.254`, `127.0.0.1`, loopback, IPv6) for domain verification or webhooks. | Strict SSRF defense rejecting private, loopback, link-local, and reserved IP ranges via `ipaddress` validation and RFC 1123 hostname checks (`apps/sites/validators.py`). | **CLOSED** |
| **T-4: Content Leakage of Drafts** | Public unauthenticated clients view unpublished or draft content. | Public content delivery endpoint explicitly queries only `status=PUBLISHED` and `published_at <= now()`. Private drafts, preview revisions, and workspace metadata are strictly excluded. | **CLOSED** |
| **T-5: Stored XSS in Structured Data** | Attacker injects malicious scripts in JSON-LD, SEO title, or metadata. | HTML entity escaping, JSON schema typing, and strict sanitization of schema values before serialization. Client integration contracts mandate safe DOM rendering (`apps/seo/services.py`). | **CLOSED** |
| **T-6: Open Redirect Attacks** | Attacker creates redirects targeting external phishing sites. | Strict redirect destination validation: relative paths only or verified domain destinations. Redirect loops and chains bounded to $\le 5$ hops (`apps/seo/validators.py`). | **CLOSED** |
| **T-7: Credential & Token Theft at Rest** | Database breach exposes search provider OAuth tokens or API keys. | Two-tier AES-256-GCM envelope encryption. Every credential has a unique Data Encryption Key (DEK) wrapped by an environment Master Key (KEK) (`apps/common/crypto.py`). Zero plain-text tokens in database. | **CLOSED** |
| **T-8: External Provider Rate Exhaustion (Denial of Service)** | Concurrent publishing triggers massive external API calls, exhausting provider quotas. | Dedicated asynchronous Celery queues with rate-limited dispatchers, capped exponential backoff with random jitter, and task deduplication (`apps/integrations/tasks.py`). | **CLOSED** |
| **T-9: Raw IP & PII Ingestion Leakage** | Stored visitor IPs or raw consent payloads violate GDPR/CCPA privacy principles. | **Zero Raw IP Persistence Guarantee:** `ConsentRecord` and `AnalyticsEvent` schemas exclude IP columns entirely. IPs are coarsened for rate-limiting and never logged or stored (`apps/analytics/models.py`). | **CLOSED** |
| **T-10: Silent Enablement of Optional Cookies** | System automatically enables newly added optional consent categories without explicit consent. | Non-silent enablement invariant (CON-5): new optional categories always default to `disabled` and require explicit visitor opt-in (`apps/consent/models.py`). | **CLOSED** |
| **T-11: Remote Code Execution on Untrusted Repos** | Attacker repository contains malicious manifests (`package.json`, scripts) executed by CMS backend. | Zero code execution invariant (GH-3): manifest files are parsed strictly as data with a 500 KB bounded limit. Zero shell subprocesses or `eval()` calls (`apps/github_integration/analyzer.py`). | **CLOSED** |
| **T-12: Destructive Git Commits to Production** | Integration automatically overwrites default branch (`main`) or deploys unreviewed code. | Invariant GH-4: PRs are strictly created on dedicated non-default branches (`cms-integration-{site_slug}`). Direct commits to base branches throw `ValidationError`. Zero auto-merge or auto-deploy. | **CLOSED** |
| **T-13: Webhook Spoofing & Replay** | Attacker sends forged GitHub webhooks or replays captured payloads. | HMAC-SHA256 signature verification over raw request body using constant-time comparison. Unique `delivery_id` tracking in `GitHubWebhookDelivery` drops replays (`apps/github_integration/views.py`). | **CLOSED** |
| **T-14: Secret & Token Leakage in Application Logs** | Sensitive tokens, passwords, private keys, or consent choices appear in routine log files. | Automated recursive redaction pattern scrubbing passwords, tokens, API keys, private keys, webhook secrets, and consent payloads in `apps/common/logging.py`. | **CLOSED** |
| **T-15: Direct Coupling to MarketIntel Internal DB** | CMS backend imports MarketIntel tables or depends on internal database schemas. | Standalone boundary maintained via external issuer adapter (`ExternalTokenIssuerAdapter`) and clean REST contracts. Zero coupling asserted by `tests/test_no_marketintel_coupling.py`. | **CLOSED** |

---

## 2. OWASP API Security Top 10 (2023) Mitigation Matrix

| OWASP API Risk | Implemented Technical Defense |
|----------------|--------------------------------|
| **API1: Broken Object Level Authorization (BOLA)** | Tenant scoping enforced in `resolve_workspace`. Users can only query objects belonging to their tenant workspace. Cross-tenant access returns 404. |
| **API2: Broken Authentication** | Cryptographically signed JWT tokens with short TTLs (15 min), rolling refresh tokens with family reuse revocation, and optional asymmetric RS256 external issuer federation. |
| **API3: Broken Object Property Level Authorization** | Serializers enforce strict read-only fields (`id`, `workspace_id`, `created_at`, audit metadata) and validate input property schemas. |
| **API4: Unrestricted Resource Consumption** | Per-endpoint DRF throttling (`AnonRateThrottle`, `UserRateThrottle`, public rate limits), bounded pagination (`PageNumberPagination` with max limits), and 500 KB manifest bounds. |
| **API5: Broken Function Level Authorization (BFLA)** | Role-based access control (`Owner`, `Admin`, `Editor`, `Analyst`) enforced via `RequireWorkspaceRole` and `IsWorkspaceAdmin`. Administrative mutations require elevated privileges. |
| **API6: Unrestricted Access to Sensitive Business Flows** | Search indexing jobs and integration PR generation are rate-limited, deduplicated, and audit-logged. |
| **API7: Server Side Request Forgery (SSRF)** | Domain verification and webhook URL dispatchers resolve IP addresses and reject loopback, link-local, private RFC 1918, and cloud metadata addresses before issuing connections. |
| **API8: Security Misconfiguration** | Production settings enforced via `check --deploy`: HSTS (1 year + subdomains + preload), SSL redirect, secure cookies, and no debug mode in production. |
| **API9: Improper Inventory Management** | All API routes versioned under `/api/v1/` and documented via OpenAPI 3.0 schema generated automatically with `drf-spectacular`. Interactive docs disabled in production. |
| **API10: Unsafe Consumption of APIs** | Third-party provider APIs (Google, Bing, GitHub) wrapped with strict payload parsers, timeout bounds, retry policies with jitter, and mock adapters for deterministic testing. |
