# Privacy Architecture, Data Minimization & Retention Policy

## 1. Privacy-by-Design Principles

The CMS Backend adheres to strict privacy-by-design principles under the EU General Data Protection Regulation (GDPR) and the California Consumer Privacy Act / CPRA:

1. **Data Minimization (GDPR Art. 5(1)(c)):** Only information strictly necessary for operational discovery, consent auditing, and aggregated analytics is ingested.
2. **Zero Raw IP Storage Guarantee (CON-3, ANA-5):** Application database tables for visitor consent (`consent_record`) and first-party analytics (`analytics_event`) **omit IP columns entirely**. IP addresses are used solely in-memory by rate limiters and are discarded immediately.
3. **No Browser Fingerprinting:** Visitor identification relies on client-generated, pseudonymous UUIDs stored in browser storage (`visitor_id`). The backend explicitly rejects hardware, canvas, or audio fingerprinting.
4. **User-Agent Coarsening:** Analytics ingestion parses user agents into coarse buckets (e.g. `Chrome/Desktop`, `Safari/Mobile`) and discards fine-grained OS build strings.

---

## 2. Ingestion & Consent Flow

```
Visitor Browser / Client
       │
       ├────────────────────────────────────────┐
       │ 1. GET /public/sites/{key}/consent-config
       │    (Fetch categories, policy version, GCM defaults)
       ▼
[ Consent Banner / UI ]
       │
       │ 2. User Selects Choices (Accept / Reject / Customize)
       │    POST /public/sites/{key}/consent
       ▼
CMS Backend: Consent Service
       │
       ├─ Validates payload, allowlisted categories, policy version
       ├─ Computes status: GRANTED, PARTIALLY_GRANTED, or DENIED
       ├─ Persists pseudonymous ConsentRecord (Zero IP stored)
       └─ Returns Google Consent Mode v2 update directives
```

### Non-Silent Enablement Invariant (CON-5)
When a site administrator creates a new custom consent category, it is initialized with `default_state=False` and `required=False`. The backend ensures existing visitors are never silently opted into new optional tracking without explicit renewed consent.

### Consent Withdrawal & Version Invalidation (CON-4)
- **Withdrawal:** A visitor can withdraw consent at any time via `POST /api/v1/public/sites/{site_slug}/consent/withdraw`. The backend marks the existing record withdrawn and suppresses optional tracking.
- **Policy Version Changes:** When a site activates a new `PrivacyPolicyVersion`, prior consent for optional categories is invalidated until the visitor records consent for the new version.

---

## 3. Data Retention & Automated Cleanup

| Data Category | Table | Default Retention | Retention Mechanism |
|---------------|-------|-------------------|---------------------|
| **Visitor Consent Records** | `consent_record` | 365 days (configurable 30–1095 days) | Nightly Celery Beat task: `cleanup_expired_consent_records` |
| **First-Party Analytics Events** | `analytics_event` | 90 days (configurable 7–730 days) | Nightly Celery Beat task: `cleanup_expired_analytics_events` |
| **Audit Log Events** | `audit_event` | 730 days (2 years) | Retained for compliance, append-only immutable |
| **Webhook Delivery IDs** | `github_webhook_delivery` | 30 days | Replay deduplication window |

---

## 4. GDPR Subject Rights (Art. 15, 17, 20)

### Right of Access & Data Portability (Art. 15, 20)
Authenticated workspace administrators can export all historical consent records associated with a specific visitor:
```http
GET /api/v1/workspaces/{workspace_id}/sites/{site_id}/consent/records/visitor/{visitor_id}/export/
```
Returns a chronological JSON payload containing all consent decisions, categories, timestamps, and withdrawal records.

### Right to Erasure / "To Be Forgotten" (Art. 17)
Authenticated workspace administrators can permanently delete all consent records for a specific visitor:
```http
DELETE /api/v1/workspaces/{workspace_id}/sites/{site_id}/consent/records/visitor/{visitor_id}/
```
Permanently deletes all matching `ConsentRecord` rows and creates an immutable audit record (`CONSENT_RECORDS_PURGED`) tracking the erasure request.
