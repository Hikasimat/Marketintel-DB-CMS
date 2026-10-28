# MarketIntel Federated Integration Guide

## 1. Overview & Decoupling Invariants

The CMS Backend is engineered as a strictly standalone service. In accordance with architectural invariant **MI-2**, the CMS backend codebase contains:
- **Zero internal database foreign keys** to MarketIntel tables.
- **Zero MarketIntel imports**, internal models, or credential schemas in core business logic.
- An automated test (`tests/test_no_marketintel_coupling.py`) continuously asserting that no business logic references internal MarketIntel modules or tables.

All future integration with MarketIntel occurs strictly through documented API contracts, asymmetric token federation, and standardized claims.

---

## 2. Token Trust & Authentication Adapter (AUTH-5, MI-1)

The backend provides an isolated external token adapter (`apps/accounts/tokens.py::ExternalTokenIssuerAdapter`). When enabled, it validates tokens issued by an external MarketIntel Identity Provider without modifying CMS domain logic:

```
[ MarketIntel DB / IdP ]
         │
         │ Issues RS256/EdDSA signed JWT
         ▼
[ CMS Backend Bearer Header ]
         │
         ▼
[ ExternalTokenIssuerAdapter ]
         │
         ├─ Verifies signature against external public key / JWKS
         ├─ Validates `iss` matches AUTH_EXTERNAL_ISSUER_NAME
         ├─ Validates `aud` matches AUTH_EXTERNAL_AUDIENCE
         └─ Maps claims to User & WorkspaceMembership
```

### Required Configuration Settings
```ini
# External Issuer Configuration
AUTH_EXTERNAL_ISSUER_ENABLED=true
AUTH_EXTERNAL_ISSUER_NAME=https://auth.marketintel.internal
AUTH_EXTERNAL_AUDIENCE=cms-backend-api
AUTH_EXTERNAL_ISSUER_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA..."
```

---

## 3. JWT Claim Mapping Specification

Tokens issued by MarketIntel must supply standard RFC 7519 claims and CMS tenant claims:

```json
{
  "iss": "https://auth.marketintel.internal",
  "sub": "usr_9b1deb4d3b7d4badac5d10ac45b00c80",
  "aud": "cms-backend-api",
  "email": "analyst@marketintel.com",
  "exp": 1793260800,
  "iat": 1793257200,
  "workspaces": [
    {
      "workspace_id": "7b58c732-45e0-496e-bc3d-f2e30c4923f1",
      "role": "OWNER"
    },
    {
      "workspace_id": "e3b0c442-98fc-1c14-9afb-4c8996fb9242",
      "role": "EDITOR"
    }
  ]
}
```

### Claim Translation Matrix
| MarketIntel JWT Claim | CMS Domain Entity | Mapping Rule |
|-----------------------|-------------------|--------------|
| `sub` | `User.id` or `User.external_subject_id` | Stable external user identifier. |
| `email` | `User.email` | Synchronized on request; normalized to lowercase. |
| `workspaces[].workspace_id` | `Workspace.id` | Resolved strictly via tenant boundaries (`resolve_workspace`). |
| `workspaces[].role` | `WorkspaceMembership.role` | Mapped to `OWNER`, `ADMIN`, `EDITOR`, or `ANALYST`. |

---

## 4. Idempotency & Mutation Operations

For service-to-service automation (e.g. MarketIntel automatically provisioning a CMS site or domain):
- **Idempotency Keys:** Mutating requests support an `Idempotency-Key: <uuid>` header. Duplicate requests within a 24-hour window return the cached initial response.
- **Error Formatting:** All API errors conform strictly to the uniform envelope (`{"error": {"code": "...", "message": "...", "request_id": "..."}}`).
- **Retry Policy:** Clients should retry 5xx and 429 responses using exponential backoff with random jitter.

---

## 5. Phased Integration Plan

1. **Phase 1 (Current — Standalone):** Local CMS authentication with pure-Python JWT rotation, deterministic mocks for external services, complete tenant isolation.
2. **Phase 2 (Federated Token Trust):** Enable `AUTH_EXTERNAL_ISSUER_ENABLED=true` in staging; verify MarketIntel RS256 token verification via `ExternalTokenIssuerAdapter`.
3. **Phase 3 (Tenant Lifecycle Webhooks):** Implement asynchronous webhooks from MarketIntel for automated customer workspace provisioning and de-provisioning.
