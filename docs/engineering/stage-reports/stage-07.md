# Stage 07 — Consent and Cookie Preference Backend

- **Date:** 2026-10-28
- **Roles performed:** Sequential role passes by a single agent (Orchestrator, Security Engineer, Backend Engineer, QA, and Independent Reviewer).

## Scope

Implement per-site consent configuration, privacy policy version management, visitor consent recording, withdrawal lifecycles, data retention cleanup, GDPR portability and erasure, and public browser contracts:
1. **Per-Site Consent Configuration (`SiteConsentConfig`, CON-1, CON-2):**
   - Configurable compliance mode (`GDPR`, `CCPA_CPRA`, `GLOBAL_OPT_IN`, `GLOBAL_OPT_OUT`).
   - Bounded retention periods (`retention_days`, 30 to 1095 days).
   - Baseline categories (`necessary`, `analytics`, `marketing`, `preferences`).
   - `necessary` category is permanently active (`required=True`, `default_state=True`) and cannot be disabled or redefined.
   - Optional categories default to disabled (`default_state=False`).
   - Extended custom category definitions with mandatory safeguards preventing silent enablement (CON-5).
   - Google Consent Mode v2 default signal configuration (`ad_storage: denied`, `analytics_storage: denied`, `ad_user_data: denied`, `ad_personalization: denied`).
2. **Privacy Policy Version Management (`PrivacyPolicyVersion`, CON-1, CON-4):**
   - Policy version strings format validation (`1.0`, `2026.1`).
   - Atomic version activation (`activate()`) deactivating prior versions and linking to the site consent config.
   - Version bump invalidation: when policy version changes, prior consent for optional categories is invalidated and suppressed until re-consented (CON-4).
3. **Visitor Consent Decision Recording (`ConsentRecord`, CON-3, CON-4):**
   - Strict validation of opaque pseudonymous `visitor_id` (regex bounded between 8 and 128 characters; no browser fingerprinting).
   - **Zero Raw IP Persistence Guarantee (CON-3, ANA-5):** `ConsentRecord` schema excludes IP columns; no IP address is ever stored.
   - Category validation: rejects missing/false `necessary` category, rejects unknown categories, rejects non-boolean values.
   - Decision status computation: `GRANTED` (all optional true), `PARTIALLY_GRANTED` (some optional true), `DENIED` (only necessary true).
   - Dynamic Google Consent Mode v2 update directives dispatching granted/denied signals based on choices.
4. **Consent Withdrawal & State Inquiry (CON-4):**
   - Public withdrawal endpoint (`POST /api/v1/public/sites/<site_slug>/consent/withdraw`) creating an immutable withdrawal record, marking prior decisions withdrawn, disabling all optional categories, and dispatching GCM denial updates.
   - Status inquiry endpoint (`GET /api/v1/public/sites/<site_slug>/consent/status`) reporting effective category states, expiry, withdrawal status, and policy version mismatch flags.
5. **GDPR Compliance & Data Retention (CON-6):**
   - GDPR Art. 15/20 data portability: `GET .../consent/records/visitor/<visitor_id>/export/` exporting complete chronological consent history for a visitor.
   - GDPR Art. 17 right to erasure: `DELETE .../consent/records/visitor/<visitor_id>/` deleting all consent records for a visitor and recording an audit event.
   - Periodic Celery retention pruning task: `cleanup_expired_consent_records` pruning records where `expires_at < now()`.
   - Aggregated consent analytics: `GET .../consent/summary/` reporting opt-in rates and category acceptance distributions.
6. **Privacy & Redaction Guarantees (CON-7):**
   - Automated redaction of `consent_payload` and `categories_payload` in `apps.common.logging.redact_sensitive`.
   - Access logging verified to leak zero raw consent payloads or sensitive parameters.
7. **Multi-Tenant Security & Anti-Enumeration (TEN-3):**
   - Cross-tenant requests to consent configuration, policy versions, audit records, export, and summary return HTTP 404 Not Found.

## Baseline (from Stage 06 commit `3fc7539`)

| Item | Finding |
|------|---------|
| Git commit | `3fc7539` ("Stage 6: GA4 reporting, first-party event ingestion, privacy coarsening, retention, tests") |
| Services | PostgreSQL 16 on 55432, Redis 7 on 56379 running healthy in Docker Compose |
| Test suite | 141 tests passing |

## Files Created and Modified

### Consent App (`apps/consent`)
- `apps/consent/__init__.py`: Package initialization.
- `apps/consent/apps.py`: Registered `ConsentConfig`.
- `apps/consent/models.py`: `SiteConsentConfig`, `PrivacyPolicyVersion`, and `ConsentRecord` (zero IP field).
- `apps/consent/validators.py`: Format validators for visitor ID, policy version string, category payload allowlists, and custom category schemas.
- `apps/consent/services.py`: Domain services for recording consent, withdrawal lifecycle, status resolution, GDPR export, and GDPR erasure.
- `apps/consent/serializers.py`: Serializers for management CRUD, public browser banner contracts, consent submission, withdrawal, and aggregation.
- `apps/consent/views.py`: Management views (config, policy versions, records, GDPR purge/export, summary) and public browser views (banner config, consent submit, withdraw, status) with CT-6 Origin checks.
- `apps/consent/urls.py`: Workspace and public URL routing.
- `apps/consent/tasks.py`: Celery task `cleanup_expired_consent_records` for automated retention cleanup.
- `apps/consent/migrations/0001_initial.py`: Database migrations applied to PostgreSQL.

### Core Configuration & Logging
- `cms/settings/base.py`: Registered `"apps.consent"`, added OpenAPI enum overrides for `ConsentRecordStatusEnum`, `ConsentTypeEnum`, `JurisdictionModeEnum`, and `GCMStateEnum`.
- `cms/urls.py`: Mounted `apps.consent.urls`.
- `apps/common/logging.py`: Added `consent_payload` and `categories_payload` to `SENSITIVE_KEY_PATTERN` automated redaction.

### Test Suites
- `tests/consent/__init__.py`: Package initialization.
- `tests/consent/test_config.py`: Configuration defaults, permissions, retention limits, and model validation (CON-1).
- `tests/consent/test_public_config.py`: Public banner config contract, origin validation, and GCM defaults (CON-2).
- `tests/consent/test_records.py`: Consent decision recording, category validation, visitor ID bounds, and GCM updates (CON-3).
- `tests/consent/test_lifecycle.py`: Withdrawal lifecycle, history preservation, and policy version bump invalidation (CON-4).
- `tests/consent/test_new_category.py`: Extension category validation and prevention of silent enablement (CON-5).
- `tests/consent/test_retention_export.py`: GDPR Art. 15/20 export, GDPR Art. 17 erasure, retention Celery task, and summary metrics (CON-6).
- `tests/consent/test_no_log_leak.py`: Sensitive redaction and verification that consent payloads are never logged (CON-7).
- `tests/security/test_idor.py`: Cross-tenant IDOR anti-enumeration tests for consent endpoints.
- `tests/content/test_public_content_api.py`: Cache clear fixture preventing rate limit bleed-through in multi-suite runs.

### Documentation & Schemas
- `docs/api/consent-and-analytics-api.md`: Comprehensive API reference for consent and analytics.
- `docs/engineering/requirements-matrix.md`: Marked CON-1 through CON-7 as `IMPLEMENTED`.
- `docs/engineering/stage-reports/stage-07.md`: Stage 7 execution report.
- `docs/engineering/stage-reports/README.md`: Updated stage index.
- `openapi.yaml`: Regenerated OpenAPI v3 schema with zero warnings.

---

## Acceptance Criteria & Evidence

| Requirement | Acceptance Criteria | Observed Evidence |
|-------------|---------------------|-------------------|
| **CON-1** | Per-site config: categories (`necessary` always on; `analytics`, `marketing`, custom default off), policy version, retention, jurisdiction flags. | `test_default_consent_config_creation_and_categories`, `test_site_consent_config_api_permissions`, and `test_retention_days_validation` pass. |
| **CON-2** | Public config endpoint (non-secret) including Consent Mode mapping contract. | `test_public_consent_config_success` and `test_public_consent_config_gcm_disabled` pass; CT-6 origin check verified by `test_public_consent_config_origin_rejection`. |
| **CON-3** | Record consent: visitor ID, categories (allowlist), policy version must match current, timestamp, expiry; accept/reject/customize. | `test_record_consent_full_opt_in`, `test_record_consent_partial_opt_in`, `test_record_consent_full_rejection_of_optional`, `test_record_consent_rejection_of_false_necessary`, `test_record_consent_rejection_of_unknown_category`, `test_record_consent_rejection_of_invalid_visitor_id` pass. Zero IP column stored. |
| **CON-4** | Withdrawal/change creates a new record; history preserved; policy version bump invalidates prior consent for optional categories. | `test_consent_withdrawal_preserves_history_and_disables_optional` and `test_policy_version_bump_invalidates_prior_consent` pass. Prior records marked withdrawn; optional categories suppressed upon policy bump until re-consent. |
| **CON-5** | Adding a new optional category never silently enables it. | `test_adding_new_category_never_silently_enables_it` passes; custom categories strictly enforce `required=False`, `default_state=False`. |
| **CON-6** | Export/delete by visitor ID (authorized and rate limited); retention cleanup job; minimal audit. | `test_visitor_consent_export_gdpr_portability`, `test_visitor_consent_purge_gdpr_erasure`, `test_retention_cleanup_celery_task`, and `test_consent_summary_metrics` pass. |
| **CON-7** | Consent payloads are never logged. | `test_redact_sensitive_handles_consent_and_categories_payload` and `test_public_consent_submission_no_log_leak` pass. |
| **TEN-3** | Cross-tenant anti-enumeration (404 Not Found on cross-tenant requests). | `test_cross_tenant_consent_access_returns_404` passes across all consent management routes. |

---

## Commands Run and Observed Results

### 1. Migrations
```powershell
.venv\Scripts\python.exe manage.py makemigrations consent
# Result: Created apps\consent\migrations\0001_initial.py

.venv\Scripts\python.exe manage.py migrate
# Result: Applying consent.0001_initial... OK
```

### 2. Automated Test Suite and Coverage
```powershell
.venv\Scripts\pytest.exe --cov=apps --cov-report=term-missing
# Result: 163 passed in 130.32s
# Overall Statement Coverage: 85%
# apps.consent coverage: 84% (models: 87%, serializers: 97%, services: 90%, tasks: 82%)
```

### 3. Static Code Analysis & Formatting
```powershell
.venv\Scripts\ruff.exe format --check .
# Result: 161 files left unchanged

.venv\Scripts\ruff.exe check .
# Result: All checks passed!

.venv\Scripts\mypy.exe apps
# Result: Success: no issues found in 88 source files
```

### 4. Static Security Scanning
```powershell
.venv\Scripts\bandit.exe -r apps -c pyproject.toml
# Result: Total issues identified: 0 (0 High, 0 Medium, 0 Low)
```

### 5. OpenAPI v3 Validation
```powershell
.venv\Scripts\python.exe manage.py spectacular --validate --fail-on-warn --file openapi.yaml
# Result: Exit code 0, zero warnings, openapi.yaml written cleanly
```

---

## External Integration Check Status

| Integration | Check Mode | Status | Details |
|-------------|------------|--------|---------|
| Google Consent Mode v2 | Deterministic Contract | `LIVE-PASS` (Contract) | Implemented documented signal dispatch contracts (`ad_storage`, `analytics_storage`, `ad_user_data`, `ad_personalization`) in public endpoints and serializers. |
| PostgreSQL 16 | Real Database | `LIVE-PASS` | Applied clean migrations, tested indexes and constraints live on port 55432. |
| Redis 7 & Celery | Cache & Broker | `LIVE-PASS` | Tested retention task execution and cache operations on port 56379. |

---

## Independent Review Findings & Remediation

1. **`record_audit_event` Argument Mismatch:**
   - *Finding:* `apps/consent/views.py` and `apps/consent/services.py` called `record_audit_event(..., actor_id=...)`, which caused a `TypeError` because the function accepts `actor: User | None = None`.
   - *Fix:* Updated calls to pass `actor=request.user if request.user.is_authenticated else None`.
2. **Django vs. DRF `ValidationError` Translation:**
   - *Finding:* `apps/consent/validators.py` originally imported `django.core.exceptions.ValidationError`, causing uncaught 500 errors instead of DRF 400 Bad Request responses when public API payloads contained illegal or unallowlisted categories.
   - *Fix:* Replaced with `from rest_framework.exceptions import ValidationError`.
3. **Throttling Bleed-Through in Multi-Suite Test Runs:**
   - *Finding:* In full multi-suite test runs, earlier public requests consumed the in-memory throttle cache, causing `test_public_origin_allowlist_enforcement` to return HTTP 429 Too Many Requests.
   - *Fix:* Added `cache.clear()` fixture at the start of public delivery tests to guarantee test isolation.
4. **RUF012 Mutable Default on Class Meta Attributes:**
   - *Finding:* `ordering = ["..."]` on `PrivacyPolicyVersion.Meta` and `ConsentRecord.Meta` triggered Ruff `RUF012`.
   - *Fix:* Annotated as `ordering: ClassVar[list[str]] = [...]`.

---

## Remaining Risks & Blockers

- None for Stage 7. The consent backend operates as a standalone, zero-PII privacy engine.
- As documented, the system provides backend contracts for site-side consent managers and SDKs; no frontend UI or client-side banner is included in this backend-only service.

---

## Gate Decision

- **Gate:** `PASS`
- **Next Stage Allowed:** `YES` (Stage 8 — Optional GitHub Repository Integration, feature-flagged).
