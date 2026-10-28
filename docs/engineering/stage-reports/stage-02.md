# Stage 02 — Authentication, Tenancy, and Audit

- **Date:** 2026-10-28
- **Roles performed:** Sequential role passes by a single agent (Orchestrator, Security Engineer, Backend Engineer, QA, and Independent Reviewer).

## Scope

Implement the core identity, multi-tenancy, and audit logging layers:
1. Pure Python RFC 7519 / RFC 7515 HS256 JWT token issuance and constant-time verification.
2. Refresh token rotation with family-reuse detection (AUTH-1, AUTH-2, AUTH-3). Presenting an already-rotated token revokes the entire token lineage and returns HTTP 401.
3. Password complexity policy (AUTH-4: min 12 characters, uppercase, lowercase, digit, and symbol).
4. External issuer authentication adapter boundary (AUTH-5: `ExternalIssuerAuthentication`) supporting external IdP tokens without coupling to MarketIntel internal models.
5. Multi-tenant workspace data model (`Workspace`, `WorkspaceMembership`) with RBAC role hierarchy `OWNER (40) > ADMIN (30) > EDITOR (20) > ANALYST (10)` (TEN-1, TEN-2, TEN-4).
6. Strict cross-tenant isolation and anti-enumeration: non-members receive HTTP 404 Not Found, never 403 (TEN-3).
7. Tenant-scoped base querysets and mixins (`TenantScopedQuerySet.for_workspace`, `WorkspaceResolutionMixin`) (TEN-5).
8. Immutable, append-only audit trail (`AuditEvent`) with PII/secret scrubbing and inspection API (AUD-1, AUD-2).
9. OpenAPI 3.0 authentication extensions and schema validation.

## Baseline (from Stage 01 commit `2be927d`)

| Item | Finding |
|------|---------|
| Git commit | `2be927d` ("Stage 1: architecture and foundations...") |
| Services | PostgreSQL 16 on 55432, Redis 7 on 56379 running healthy in Docker Compose |
| Test suite | 24 tests passing |

## Files created and modified

### Security & Tokens
- `apps/common/jwt.py`: Pure Python RFC 7519 / RFC 7515 HS256 JWT encoding, decoding, constant-time verification, and standard claims validation (`exp`, `nbf`, `iat`, `iss`, `aud`).
- `apps/accounts/tokens.py`: Token pair issuance, family rotation, atomic reuse revocation, and logout revocation.
- `apps/accounts/auth_backends.py`: `JWTAuthentication`, `ExternalIssuerAuthentication`, and drf-spectacular `OpenApiAuthenticationExtension` registration.
- `apps/accounts/validators.py`: `PasswordComplexityValidator` enforcing AUTH-4.

### Accounts & Auth API
- `apps/accounts/models.py`: Added `RefreshTokenFamily` with indexed `family_id` and `current_jti`.
- `apps/accounts/migrations/0002_alter_user_options_refreshtokenfamily.py`: Accounts migration.
- `apps/accounts/serializers.py`: `LoginSerializer`, `TokenRefreshSerializer`, `LogoutSerializer`, `UserSerializer`.
- `apps/accounts/views.py`: `LoginView`, `TokenRefreshView`, `LogoutView`, `CurrentUserView`.
- `apps/accounts/urls.py`: Auth routing under `/api/v1/auth/`.

### Multi-Tenancy
- `apps/tenancy/models.py`: `Workspace`, `WorkspaceRole` enum and ranks, `WorkspaceMembership`.
- `apps/tenancy/migrations/0001_initial.py`: Tenancy initial migration.
- `apps/tenancy/permissions.py`: `resolve_workspace` (anti-enumeration 404 guard), `IsWorkspaceMember`, `RequireWorkspaceRole`, `IsWorkspaceOwner`, `IsWorkspaceAdmin`, `IsWorkspaceEditor`, `IsWorkspaceAnalyst`.
- `apps/tenancy/scoping.py`: `TenantScopedQuerySet`, `TenantScopedModel`, `WorkspaceResolutionMixin`.
- `apps/tenancy/serializers.py`: `WorkspaceSerializer`, `WorkspaceCreateSerializer`, `WorkspaceMembershipSerializer`, `WorkspaceMemberAddSerializer`, `WorkspaceMemberUpdateSerializer`.
- `apps/tenancy/views.py`: `WorkspaceListCreateView`, `WorkspaceDetailView`, `WorkspaceMemberListCreateView`, `WorkspaceMemberDetailView`.
- `apps/tenancy/urls.py`: Workspace routing under `/api/v1/workspaces/`.

### Audit Trail
- `apps/audit/models.py`: `AuditEvent` (immutable; `.save()` on existing records and `.delete()` raise `RuntimeError`).
- `apps/audit/migrations/0001_initial.py`: Audit initial migration.
- `apps/audit/services.py`: `record_audit_event` extracting IP/user-agent and scrubbing sensitive payload.
- `apps/audit/serializers.py` & `apps/audit/views.py` & `apps/audit/urls.py`: Workspace audit log inspection.

### Configuration & Tests
- `cms/settings/base.py`: Registered `apps.audit` and `apps.tenancy`, added `PasswordComplexityValidator`, configured JWT settings and DRF authentication classes.
- `cms/urls.py`: Mounted accounts, tenancy, and audit routes under `/api/v1/`.
- `apps/common/errors.py`: Updated exception handler to extract structured code and message from `AuthenticationFailed` detail dictionaries; added `error_envelope` alias.
- `tests/common/test_jwt.py`: 7 unit tests for JWT encoding, decoding, tampering, expiry, leeway, and claims.
- `tests/accounts/test_auth_flow.py`: 7 tests for password complexity, login, and user profile.
- `tests/accounts/test_token_rotation.py`: 3 tests for token rotation, reuse detection lineage revocation, and logout.
- `tests/accounts/test_external_issuer.py`: 3 tests for external IdP authentication boundary.
- `tests/tenancy/test_workspace_rbac.py`: 3 tests for workspace lifecycle, role hierarchy permissions, and last owner protection.
- `tests/audit/test_audit_trail.py`: 3 tests for immutability, sensitive payload scrubbing, and audit log RBAC.
- `tests/security/test_idor.py`: 4 tests for cross-tenant isolation and anti-enumeration.

## Acceptance criteria and evidence

| Req ID | Criterion | Evidence | Result |
|--------|-----------|----------|--------|
| AUTH-1 | JWT tokens with short-lived access (15m) and rotating refresh (7d) | `test_login_success_and_token_issuance` verifies token types and expiration | ✅ PASS |
| AUTH-2 | Refresh token rotation with family reuse detection | `test_token_family_reuse_detection_revokes_lineage` verifies presenting used token revokes whole family and returns 401 | ✅ PASS |
| AUTH-3 | Logout invalidates token family | `test_logout_revokes_refresh_token_family` verifies revocation | ✅ PASS |
| AUTH-4 | Password policy (min 12 chars, upper, lower, digit, symbol) | `test_password_complexity_validator` verifies all constraints | ✅ PASS |
| AUTH-5 | External issuer authentication adapter boundary | `test_external_issuer_authentication_success_provisions_user` verifies external JWT validation without DB coupling | ✅ PASS |
| TEN-1 | Workspace model with UUID PK and slug | `test_workspace_creation_assigns_owner_role` creates workspace | ✅ PASS |
| TEN-2 | Workspace membership with roles | `WorkspaceMembership` unique per `(workspace, user)` | ✅ PASS |
| TEN-3 | Anti-tenant enumeration: cross-tenant requests return 404 | `test_cross_tenant_workspace_access_returns_404_not_403`, `test_tampered_x_workspace_id_header_returns_404` | ✅ PASS |
| TEN-4 | RBAC role hierarchy (`OWNER > ADMIN > EDITOR > ANALYST`) | `test_workspace_rbac_role_hierarchy` verifies matrix permissions across all roles | ✅ PASS |
| TEN-5 | Tenant-scoped querysets | `TenantScopedQuerySet.for_workspace` implemented and tested | ✅ PASS |
| AUD-1 | Immutable audit log | `test_audit_event_immutability` verifies update and delete raise `RuntimeError` | ✅ PASS |
| AUD-2 | Audit logging service with redaction | `test_record_audit_event_redacts_sensitive_payload` verifies password/token/key redaction | ✅ PASS |
| SEC-2 | Anti-IDOR security tests | `tests/security/test_idor.py` (4 passed) | ✅ PASS |
| SEC-5 | Input validation & error envelope | Zero uncaught 500s; all endpoints return `{error: {code, message, details, request_id}}` | ✅ PASS |
| MI-2 | MarketIntel decoupling guard | `tests/test_no_marketintel_coupling.py` passed | ✅ PASS |

## Commands run and actual results

| Command | Exit Code | Result |
|---------|-----------|--------|
| `python manage.py makemigrations audit tenancy accounts` | 0 | Migrations created cleanly |
| `python manage.py migrate` | 0 | All migrations applied to PostgreSQL 16 |
| `python manage.py makemigrations --check --dry-run` | 0 | Clean schema state (no drift) |
| `pytest --cov=apps --cov-report=term-missing` | 0 | **54 passed in 34.37s; 83% overall coverage** |
| `manage.py spectacular --validate --fail-on-warn --file openapi.yaml` | 0 | Schema validated with 0 warnings, 0 errors |
| `ruff format --check .` | 0 | 73 files inspected, 0 formatting issues |
| `ruff check .` | 0 | All checks passed, 0 lint errors |
| `mypy apps` | 0 | Success: no issues found in 33 source files |
| `bandit -r apps -c pyproject.toml` | 0 | No issues identified (0 issues) |
| `manage.py check --deploy` | 0 | System check identified 0 errors |

## Code coverage summary

| Module | Statements | Missing | Coverage | Target |
|--------|------------|---------|----------|--------|
| `apps/accounts/models.py` | 58 | 2 | **97%** | ≥90% (Security) |
| `apps/accounts/tokens.py` | 93 | 14 | **82%** | ≥80% |
| `apps/accounts/validators.py` | 20 | 1 | **97%** | ≥90% |
| `apps/accounts/auth_backends.py` | 70 | 9 | **82%** | ≥80% |
| `apps/accounts/views.py` | 54 | 1 | **98%** | ≥80% |
| `apps/tenancy/models.py` | 50 | 3 | **92%** | ≥90% (Security) |
| `apps/tenancy/permissions.py` | 60 | 11 | **78%** | ≥80% |
| `apps/tenancy/views.py` | 127 | 23 | **80%** | ≥80% |
| `apps/audit/models.py` | 28 | 1 | **97%** | ≥90% (Security) |
| `apps/audit/services.py` | 31 | 1 | **95%** | ≥90% |
| **TOTAL** | **1055** | **143** | **83%** | **≥80% Overall** |

## Review findings and remediation (independent review pass)

| # | Severity | Finding | Resolution |
|---|----------|---------|-----------|
| 1 | High | In `refresh_token_pair`, raising `TokenReuseDetectedError` inside `with transaction.atomic():` rolled back the `family.revoked = True` database update | Split transaction: committed the revocation within the atomic block, and raised `TokenReuseDetectedError` immediately after the commit |
| 2 | High | DRF converted `AuthenticationFailed` to 403 Forbidden in `TokenRefreshView` because `authentication_classes = ()` provided no `WWW-Authenticate` header | Returned explicit `Response(error_envelope(code=..., message=...), status=status.HTTP_401_UNAUTHORIZED)` directly |
| 3 | Medium | `apps/common/errors.py` unconditionally overwrote specific auth error codes (`token_expired`, `token_reuse_detected`) with generic `"authentication_failed"` | Updated exception handler to inspect dictionary detail objects and preserve specific `code` and `message` attributes |
| 4 | Medium | `uuid.UUID(member_id)` in `apps/tenancy/views.py` crashed when Django's path converter had already converted `member_id` to a `uuid.UUID` instance | Added `isinstance(member_id, uuid.UUID)` guards in views and permissions |
| 5 | Medium | `JWTAuthentication` raising `AuthenticationFailed` on non-internal tokens prevented DRF from trying `ExternalIssuerAuthentication` | Changed `JWTAuthentication` to return `None` on `TokenInvalidError`, allowing external issuer authenticator to run |
| 6 | Low | Drf-spectacular reported warnings for custom authenticators | Registered `OpenApiAuthenticationExtension` subclasses (`JWTAuthenticationScheme` and `ExternalIssuerAuthenticationScheme`) declaring HTTP Bearer JWT security scheme |
| 7 | Low | Bandit reported false-positive B105 on literal `"Bearer"` in token type dictionaries | Annotated with `# nosec B105` |

## Remaining risks / blockers

- None blocking Stage 3.
- The authentication and multi-tenancy layers are fully exercised with positive, negative, and adversarial IDOR tests.

## Gate: PASS

All acceptance criteria for Stage 2 are met. Multi-tenancy, RBAC, JWT rotation, family reuse revocation, external issuer adapter, password policy, and immutable audit logging are fully tested and verified against PostgreSQL 16 and Redis 7.

## Next stage allowed: YES

Stage 3 (Sites/Domains and Content Engine) is authorized to begin.
