# Consent and Analytics API Specification

## 1. Overview & Privacy Principles

The CMS Backend provides privacy-first, multi-tenant Consent Management and Analytics APIs.
The system adheres to strict data protection standards:

- **Zero Raw IP Persistence (CON-3, ANA-5):** Client IP addresses are never saved to database tables or routinely logged.
- **User-Agent De-Identification (ANA-5):** Client user-agent strings are coarsened to device categories (`DESKTOP`, `MOBILE`, `TABLET`, `BOT`, `UNKNOWN`) and browser families (`CHROME`, `FIREFOX`, `SAFARI`, `EDGE`, `OTHER`). Raw user-agents are discarded immediately.
- **Pseudonymous Visitor Identification (CON-3, ANA-5):** Visitors are tracked solely using opaque client-generated identifiers (UUID / hex format). Browser fingerprinting is strictly forbidden.
- **Strict Category Gating (CON-5, ANA-6):** Essential (`necessary`) cookies are always active. Optional categories (`analytics`, `marketing`, `preferences`) default to `False`. Adding new categories never silently enables them. First-party analytics event ingestion is blocked unless explicit consent or documented legal basis is present.
- **Google Consent Mode v2 Support (CON-2):** Default GCM signals (`ad_storage`, `analytics_storage`, `ad_user_data`, `ad_personalization`) and dynamic update payloads for browser loaders.
- **Right to Erasure & Portability (CON-6, ANA-7):** GDPR Article 17 right-to-be-forgotten deletion endpoints and Article 15/20 portability export endpoints.

---

## 2. Public Browser & SDK Endpoints (CT-6 Protected)

All public endpoints validate the browser `Origin` header against the site's configured `allowed_origins` allowlist.

### 2.1 Get Public Consent Banner Configuration
- **Method:** `GET`
- **Path:** `/api/v1/public/sites/{site_slug}/consent/banner-config` (or `/api/v1/public/sites/{site_slug}/consent-config`)
- **Headers:** `Origin: https://mysite.com`
- **Response:** `200 OK`
```json
{
  "is_enabled": true,
  "jurisdiction_mode": "GDPR",
  "cookie_domain": ".mysite.com",
  "active_policy": {
    "id": "7b58c731-8c46-4cb2-8321-df5c1b69801a",
    "version": "1.0",
    "title": "Privacy Policy v1.0",
    "summary": "Initial policy release",
    "body": "# Privacy Policy\n\nWe respect your privacy...",
    "effective_date": "2026-10-28T00:00:00Z"
  },
  "categories": {
    "necessary": {
      "title": "Strictly Necessary",
      "description": "Essential cookies required for security and core functionality.",
      "required": true,
      "default_state": true
    },
    "analytics": {
      "title": "Analytics & Performance",
      "description": "Helps us improve website experience by reporting aggregated data.",
      "required": false,
      "default_state": false
    },
    "marketing": {
      "title": "Marketing & Advertising",
      "description": "Used to deliver tailored campaigns.",
      "required": false,
      "default_state": false
    },
    "preferences": {
      "title": "Functional & Preferences",
      "description": "Remembers language and theme preferences.",
      "required": false,
      "default_state": false
    }
  },
  "default_states": {
    "necessary": true,
    "analytics": false,
    "marketing": false,
    "preferences": false
  },
  "gcm_enabled": true,
  "gcm_defaults": {
    "analytics_storage": "denied",
    "ad_storage": "denied",
    "ad_user_data": "denied",
    "ad_personalization": "denied"
  }
}
```

### 2.2 Submit Visitor Consent Decision
- **Method:** `POST`
- **Path:** `/api/v1/public/sites/{site_slug}/consent`
- **Headers:** `Origin: https://mysite.com`, `Content-Type: application/json`
- **Payload:**
```json
{
  "visitor_id": "c7a8e291-5f2b-43d9-b684-28b7e2839b0a",
  "policy_version": "1.0",
  "categories": {
    "necessary": true,
    "analytics": true,
    "marketing": false,
    "preferences": true
  },
  "consent_type": "EXPLICIT_OPT_IN"
}
```
- **Response:** `201 Created`
```json
{
  "status": "RECORDED",
  "record_id": "8d32b504-2dfa-4a67-b501-1b2c4e6a8d0f",
  "decision_status": "PARTIALLY_GRANTED",
  "categories": {
    "necessary": true,
    "analytics": true,
    "marketing": false,
    "preferences": true
  },
  "gcm_update": {
    "analytics_storage": "granted",
    "ad_storage": "denied",
    "ad_user_data": "denied",
    "ad_personalization": "denied"
  }
}
```

### 2.3 Withdraw Consent
- **Method:** `POST`
- **Path:** `/api/v1/public/sites/{site_slug}/consent/withdraw`
- **Payload:**
```json
{
  "visitor_id": "c7a8e291-5f2b-43d9-b684-28b7e2839b0a"
}
```
- **Response:** `200 OK`
```json
{
  "status": "WITHDRAWN",
  "record_id": "3b21c409-5efa-4911-85bc-91024e12c124",
  "categories": {
    "necessary": true,
    "analytics": false,
    "marketing": false,
    "preferences": false
  },
  "gcm_update": {
    "analytics_storage": "denied",
    "ad_storage": "denied",
    "ad_user_data": "denied",
    "ad_personalization": "denied"
  }
}
```

### 2.4 Query Visitor Consent Status
- **Method:** `GET`
- **Path:** `/api/v1/public/sites/{site_slug}/consent/status?visitor_id={visitor_id}`
- **Response:** `200 OK`
```json
{
  "has_consent_record": true,
  "record_id": "8d32b504-2dfa-4a67-b501-1b2c4e6a8d0f",
  "status": "PARTIALLY_GRANTED",
  "categories": {
    "necessary": true,
    "analytics": true,
    "marketing": false,
    "preferences": true
  },
  "policy_version": "1.0",
  "requires_reconsent": false,
  "is_withdrawn": false
}
```

---

## 3. Workspace Management Endpoints

All management endpoints require JWT Authentication and Workspace RBAC membership.

### 3.1 Get / Update Site Consent Configuration
- `GET /api/v1/workspaces/{workspace_id}/sites/{site_id}/consent/config/`
- `PATCH /api/v1/workspaces/{workspace_id}/sites/{site_id}/consent/config/` (Admin / Owner only)

### 3.2 Privacy Policy Versions
- `GET /api/v1/workspaces/{workspace_id}/sites/{site_id}/consent/versions/`
- `POST /api/v1/workspaces/{workspace_id}/sites/{site_id}/consent/versions/` (Admin / Owner only)
- `POST /api/v1/workspaces/{workspace_id}/sites/{site_id}/consent/versions/{version_id}/activate/` (Admin / Owner only)

### 3.3 Compliance Records & GDPR
- `GET /api/v1/workspaces/{workspace_id}/sites/{site_id}/consent/records/` (Paginated, filterable)
- `GET /api/v1/workspaces/{workspace_id}/sites/{site_id}/consent/records/visitor/{visitor_id}/export/` (GDPR Art. 15/20 portability)
- `DELETE /api/v1/workspaces/{workspace_id}/sites/{site_id}/consent/records/visitor/{visitor_id}/` (GDPR Art. 17 right to erasure)
- `GET /api/v1/workspaces/{workspace_id}/sites/{site_id}/consent/summary/` (Aggregated statistics)
