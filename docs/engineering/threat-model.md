# Threat Model

**Method:** STRIDE per trust boundary, plus OWASP API Security Top 10 (2023) mapping.
**Status:** Stage 0 baseline. Each stage updates the `Status` of the threats it addresses. Stage 9 closes the model.

## 1. Assets

| Asset | Sensitivity |
|-------|------------|
| Provider OAuth refresh/access tokens, Bing API keys, GitHub App private key | Critical |
| Signing keys (JWT), field-encryption KEKs, Django `SECRET_KEY` | Critical |
| User credentials, refresh tokens, invitation tokens | High |
| Draft/unpublished content, private repository contents | High |
| Consent records, analytics events (pseudonymous personal data) | High (privacy) |
| Tenant membership/role data, audit log | High (integrity) |
| Published content, SEO metadata | Low confidentiality, high integrity |

## 2. Trust boundaries

1. **Internet → public API** (anonymous: delivery, sitemap, consent, events)
2. **Internet → management API** (JWT-authenticated users / external issuer)
3. **API/worker → external providers** (Google, Bing, IndexNow, GitHub, DNS)
4. **Provider → webhooks** (GitHub)
5. **API/worker → PostgreSQL/Redis** (internal network)
6. **Customer-controlled data → processing** (schemas, content, JSON-LD, repo files, DNS answers, provider responses)

## 3. Threats and mitigations

| ID | STRIDE | Threat | Mitigation | Verification | Stage | Status |
|----|--------|--------|-----------|--------------|-------|--------|
| T-01 | E/I | Cross-tenant IDOR via guessed/leaked UUIDs | Mandatory scoped querysets; 404 for out-of-scope; generated IDOR tests for every family | `tests/security/test_idor.py` | 2+ | OPEN |
| T-02 | E | Role escalation (ADMIN grants OWNER, EDITOR edits credentials) | Role matrix in permission classes; last-owner rule; matrix tests | `test_role_matrix.py` | 2 | OPEN |
| T-03 | S | Credential stuffing / brute force | Throttles per IP + per account, constant-time password check, generic errors | `test_auth_throttle.py` | 2 | OPEN |
| T-04 | S | Refresh token theft/replay | Rotation + blacklist + family revocation on reuse; short access TTL | `test_auth_tokens.py` | 2 | OPEN |
| T-05 | S | Forged external JWT (`alg=none`, HS/RS confusion, wrong iss/aud) | Algorithm allowlist, JWKS, iss/aud/exp/nbf checks, disabled by default | `test_external_issuer.py` | 2 | OPEN |
| T-06 | I/E | SSRF via domain/URL inputs (metadata 169.254.169.254, localhost, internal services), DNS rebinding, redirect to private IP | No URL fetching for verification (DNS TXT only); `SafeClient`: resolve → validate all IPs → connect to pinned IP → revalidate every redirect hop; v4/v6/mapped/CGNAT/reserved blocklist; timeouts; size caps | `test_ssrf.py` | 3 | OPEN |
| T-07 | T | Domain takeover: claiming another tenant's domain | DNS TXT challenge with CSPRNG token; verified-domain uniqueness across tenants; periodic re-verification; lose verification → disable integrations | `test_dns_verification.py` | 3 | OPEN |
| T-08 | I | Draft/private content leak via public API, sitemap, indexing, errors | Public querysets filter on published revision only; separate public serializers; sitemap/indexing eligibility function shared and tested | `test_public_delivery.py`, `test_sitemap.py` | 3–5 | OPEN |
| T-09 | T | Stored XSS via SEO metadata / JSON-LD rendered by customer site | Strict schemas, length limits, JSON-LD script-safe serialization, documented rendering contract (escape as text) | `test_jsonld.py` | 4 | OPEN |
| T-10 | T | Open redirect / redirect loops | Same-site or allowlisted destinations; loop + chain detection | `test_redirects.py` | 4 | OPEN |
| T-11 | D | Schema bombs: deeply nested content schema/JSON payloads | Schema DSL limits (depth, field count, size); request body caps | `test_content_types.py`, `test_resource_bounds.py` | 3 | OPEN |
| T-12 | I | OAuth token leakage (logs, responses, URLs, DB dump) | Envelope encryption, never serialized, redaction processor, no tokens in query strings | `test_crypto.py`, `test_secret_leakage.py` | 5 | OPEN |
| T-13 | S/T | OAuth CSRF / code injection / redirect URI manipulation | Single-use state bound to user+site+provider, PKCE, exact redirect allowlist | `test_google_oauth.py` | 5–6 | OPEN |
| T-14 | D | Provider quota exhaustion / abuse via job triggering | Per-site job quotas, dedupe, idempotency keys, provider-level rate limit | `test_jobs.py` | 5 | OPEN |
| T-15 | R | Misrepresentation: claiming "indexed" after submission | Status vocabulary excludes `indexed` except from inspection results | `test_gsc_adapter.py` | 5 | OPEN |
| T-16 | D/T | Event ingestion flooding / data poisoning | Throttles per site + per pseudonymous ID, payload caps, allowlists, Origin check (defense in depth), per-site daily quota | `test_ingest.py` | 6 | OPEN |
| T-17 | I | PII in analytics (IPs, emails in URLs/properties) | No IP column; URL query stripping/allowlist; PII pattern rejection; UA coarsening | `test_privacy.py` | 6 | OPEN |
| T-18 | T/R | Consent forgery / tracking before consent | Policy version check, append-only records, ingestion gated on consent state, documented client contract | `test_consent_gating.py` | 6–7 | OPEN |
| T-19 | I | Consent/analytics data retained too long | Retention jobs + tests; deletion by visitor ID | `test_retention*.py` | 6–7 | OPEN |
| T-20 | E | Malicious repo content: path traversal, symlinks, huge files, crafted manifests, code execution | Never execute; API-only reads via GitHub contents/trees; path normalization; size/count caps; symlink/submodule skip; JSON parse only | `test_detection_hostile.py` | 8 | OPEN |
| T-21 | T | Writing to customer default/protected branches | Only create new branch + PR; refuse if target == default; no merge API usage | `test_pr_flow.py` | 8 | OPEN |
| T-22 | S | Forged/replayed GitHub webhooks | HMAC-SHA256 constant-time compare; delivery-ID dedupe | `test_webhooks.py` | 8 | OPEN |
| T-23 | I | Secrets committed to repo | `.gitignore`, `.env.example` placeholders only, gitleaks in CI | CI | 1 | OPEN |
| T-24 | I | Verbose errors/stack traces in prod | Error envelope, `DEBUG=False`, `check --deploy` | `test_errors.py`, CI | 1 | OPEN |
| T-25 | D | Unbounded list queries / N+1 | Pagination caps, `assertNumQueries` guards | `test_query_bounds.py` | 3+ | OPEN |
| T-26 | S | CORS misconfiguration treated as auth | Explicit allowlists, no `*` with credentials; public API needs no credentials | `test_cors.py` | 1, 3 | OPEN |
| T-27 | T | Supply-chain compromise | Pinned deps with hashes where feasible, pip-audit, minimal deps | CI | 1, 9 | OPEN |
| T-28 | E | Suspended workspace/site continues to act (jobs, public API) | Status checks in services and jobs | `test_suspension.py` | 2–3 | OPEN |
| T-29 | I | Timing/enumeration on login, invitations, public site keys | Generic errors, constant-time compare, unguessable keys | auth tests | 2–3 | OPEN |
| T-30 | R | Missing audit trail for sensitive changes | `record_audit()` in services; tests assert audit rows | `test_audit_events.py` | 2+ | OPEN |

## 4. OWASP API Top 10 (2023) mapping

| Risk | Threat IDs |
|------|-----------|
| API1 Broken Object Level Authorization | T-01, T-08 |
| API2 Broken Authentication | T-03, T-04, T-05 |
| API3 Broken Object Property Level Authorization | T-08, T-12 (serializer field allowlists) |
| API4 Unrestricted Resource Consumption | T-11, T-14, T-16, T-25 |
| API5 Broken Function Level Authorization | T-02 |
| API6 Unrestricted Access to Sensitive Business Flows | T-14, T-16 |
| API7 SSRF | T-06 |
| API8 Security Misconfiguration | T-24, T-26 |
| API9 Improper Inventory Management | OpenAPI as source of truth; versioning policy |
| API10 Unsafe Consumption of APIs | Provider response validation (T-15, malformed-response tests), T-20 |

## 5. Residual / accepted risks (to be confirmed at Stage 9)

- Public `public_site_key` is enumerable from customer sites by design; it grants only public data.
- Pseudonymous visitor IDs are personal data in many jurisdictions; customers remain responsible for their lawful basis (documented, not certified).
- Live provider behavior is verified only when credentials are supplied. Otherwise it is mock-verified and marked `BLOCKED`.
