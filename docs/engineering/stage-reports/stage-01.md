# Stage 01 — Project Foundation and Baseline Architecture

- **Date:** 2026-10-28
- **Roles performed:** Sequential role passes by a single agent (Orchestrator, Infrastructure/DevOps Engineer, Backend Foundations Engineer, Security Engineer, QA, and Independent Reviewer).

## Scope

Establish the production foundational runtime, containerization, environment configuration, database and cache connectivity, structured logging with PII/secret redaction, correlation IDs, uniform error envelopes, health probes, OpenAPI schema generation, base user model, test harnesses, CI pipeline, and security scanning tools. No domain models or business logic (tenancy, content, SEO, search) were implemented in this stage.

## Baseline (from Stage 00 commit `94a7bf6`)

| Item | Finding |
|------|---------|
| Git commit | `94a7bf6` ("Stage 0: discovery and planning documents") |
| Python | CPython 3.13.6 selected for `.venv` (clean compatibility with Django 5.2 LTS, psycopg 3, redis, celery) |
| Docker | Docker Desktop 4.x running; Docker engine `29.7.2`, Compose `v5.4.0` |
| Tests at baseline | 0 tests (N/A) |

## Files created and modified

### Infrastructure & Configuration
- `.gitignore` (updated with local test/coverage/cache artifacts)
- `.gitattributes` (LF line ending normalization)
- `docker-compose.yml` (PostgreSQL 16 on 55432, Redis 7 on 56379, api service definition)
- `Dockerfile` (multi-stage unprivileged Debian-slim container)
- `.env.example` (template with production & dev settings placeholders)
- `pyproject.toml` (ruff, pytest, coverage, mypy, bandit configurations)
- `.github/workflows/ci.yml` (multi-job CI workflow with lint, typecheck, security audit, postgres/redis services, test suite, and openapi validation)
- `README.md` (updated with production backend architecture and quickstart instructions)

### Dependencies
- `requirements/base.in` & `requirements/base.txt` (pinned Django 5.2.18, DRF 3.18.3, drf-spectacular 0.30.0, psycopg 3.3.6, celery 5.6.3, redis 6.4.0, django-cors-headers 4.9.0, gunicorn 23.0.0)
- `requirements/dev.in` & `requirements/dev.txt` (pinned pytest 9.2.0, pytest-django 4.14.0, pytest-cov 7.1.0, ruff 0.17.3, mypy 2.4.0, django-stubs 6.1.2, djangorestframework-stubs 3.18.1, bandit 1.9.4, pip-audit 2.10.1)
- `docs/engineering/dependencies.md` (justification matrix for all third-party libraries)

### Core Settings & Apps
- `manage.py`
- `cms/wsgi.py` & `cms/asgi.py`
- `cms/urls.py` (versioned routing `/api/v1/`, health endpoints `/livez` & `/readyz`, OpenAPI docs `/api/schema/`)
- `cms/settings/env.py` (fail-fast environment variable parser with bulk validation)
- `cms/settings/base.py` (PostgreSQL-only, Redis cache, JSON structured logging, DRF deny-by-default, CORS origin validation)
- `cms/settings/dev.py` & `cms/settings/prod.py` & `cms/settings/test.py`
- `apps/common/logging.py` (structured JSON logging, `RequestContextFilter`, and regex/key-based `redact_sensitive` processor for tokens, bearer strings, passwords, and secrets)
- `apps/common/middleware.py` (`RequestIDMiddleware` for tracing correlation IDs and `AccessLogMiddleware`)
- `apps/common/errors.py` (uniform `{error: {code, message, details, request_id}}` envelope and DRF custom exception handler)
- `apps/common/pagination.py` (`DefaultPagination` capped at 100 items per page)
- `apps/common/health.py` (`LiveCheckView` for process liveness and `ReadyCheckView` verifying PostgreSQL cursor and Redis ping)
- `apps/accounts/models.py` (custom `User` model with UUID PK, lowercase email username, timestamped audit mixins)
- `apps/accounts/migrations/0001_initial.py` (initial accounts migration)

### Test Harness & Test Suites
- `tests/conftest.py`
- `tests/common/test_settings_validation.py` (fail-fast env parser test cases)
- `tests/common/test_logging_redaction.py` (sensitive token/password/header redaction tests)
- `tests/common/test_errors.py` (uniform envelope tests across validation, auth, not found, unhandled 500)
- `tests/common/test_health.py` (liveness and readiness tests with healthy/unhealthy DB & Redis)
- `tests/common/test_openapi.py` (schema generation tests)
- `tests/accounts/test_user_manager.py` (custom User creation, normalisation, and superuser validation)
- `tests/test_no_marketintel_coupling.py` (architecture guard preventing MarketIntel imports or dependencies)

## Acceptance criteria and evidence

| Criterion (skill Stage 1 gate) | Evidence | Result |
|-------------------------------|----------|--------|
| PostgreSQL 16 & Redis 7 running via Compose | `docker compose ps` shows `cms_postgres` (healthy on 55432) and `cms_redis` (healthy on 56379) | ✅ PASS |
| Clean migrations on PostgreSQL | `python manage.py migrate` exited 0; `makemigrations --check --dry-run` shows no drift | ✅ PASS |
| Fail-fast environment parser (FND-1) | `cms/settings/env.py` reports all missing/malformed vars at once without leaking secret values; 6 unit tests passing | ✅ PASS |
| Health endpoints (FND-2) | `/livez` returns 200 `{"status": "live"}`; `/readyz` tests DB cursor & Redis ping, returns 200 or 503 without leaking stack traces | ✅ PASS |
| Uniform error envelope (FND-4) | `{error: {code, message, details, request_id}}` returned on 400, 401, 403, 404, 405, 500; 4 tests passing | ✅ PASS |
| Structured logging & PII redaction (FND-5) | `apps/common/logging.py` redacts `password`, `token`, `secret`, `api_key`, `Bearer ...`; correlation IDs propagated via `RequestContextFilter`; 3 tests passing | ✅ PASS |
| Security headers & deny-by-default (SEC-2, SEC-5) | DRF `DEFAULT_PERMISSION_CLASSES = [IsAuthenticated]`, `HSTS`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` | ✅ PASS |
| Architecture boundary guard (MI-2) | `tests/test_no_marketintel_coupling.py` enforces zero imports from `marketintel` | ✅ PASS |
| OpenAPI schema valid | `manage.py spectacular --validate --fail-on-warn` exited 0 with 0 warnings, 0 errors; openapi.yaml generated | ✅ PASS |
| Test suite execution & coverage | 24 passed in 9.76s; 84% total coverage (>=80% target), 100% on `apps/accounts/models.py` (>=90% target) | ✅ PASS |
| Static analysis & linting | Ruff format & check clean (0 errors); Mypy clean (0 errors); Bandit clean (0 issues) | ✅ PASS |

## Commands run and actual results

| Command | Exit Code | Result |
|---------|-----------|--------|
| `docker compose up -d` | 0 | Postgres 16 and Redis 7 started and healthy |
| `python manage.py migrate` | 0 | All migrations applied cleanly to PostgreSQL 16 |
| `python manage.py makemigrations --check --dry-run` | 0 | No changes detected (clean schema state) |
| `pytest --cov=apps --cov-report=term-missing` | 0 | 24 passed in 9.76s; 84% coverage |
| `manage.py spectacular --validate --fail-on-warn --file openapi.yaml` | 0 | Schema validated with 0 warnings |
| `ruff format --check .` | 0 | 43 files inspected, 0 formatting issues |
| `ruff check .` | 0 | All checks passed, 0 lint errors |
| `mypy apps/common apps/accounts` | 0 | Success: no issues found in 10 source files |
| `bandit -r apps -c pyproject.toml` | 0 | 0 issues across all severities |
| `DJANGO_SETTINGS_MODULE=cms.settings.prod python manage.py check --deploy` | 0 | System check identified no issues (0 silenced) |

## Review findings and remediation (independent review pass)

| # | Severity | Finding | Resolution |
|---|----------|---------|-----------|
| 1 | High | Class attribute mutation in `User.REQUIRED_FIELDS` and `health.py` permission tuples flagged by Ruff (RUF012) | Applied `ClassVar[list[str]]` annotation and converted view permission classes to immutable tuples |
| 2 | High | `manage.py spectacular` failed on `LiveCheckView` and `ReadyCheckView` because plain `APIView` lacked serializers | Excluded health probes from the external OpenAPI client schema via `@extend_schema(exclude=True)` |
| 3 | Medium | Settings `_required_marker` variable was referenced before definition when importing `prod.py` | Refactored marker to `REQUIRED if is_prod else None` |
| 4 | Medium | Mypy flagged type shadowing of `str` and `bool` inside `class Env` | Aliased module-level types `_Str = str`, `_Bool = bool` |
| 5 | Medium | Mypy flagged unsafe attribute access on DRF `Throttled` and `DefaultPagination` page initialization | Added explicit safe `getattr(exc, "wait", None)` and defensive page null checks |
| 6 | Low | Bandit flagged `assert` statement in `apps/common/pagination.py` (B101) | Replaced `assert` with explicit `RuntimeError` |

## Remaining risks / blockers

- None blocking Stage 2.
- Local Docker containers are mapped to ports 55432 and 56379; `.env.example` documents these ports.

## Gate: PASS

All acceptance criteria for Stage 1 are met. PostgreSQL and Redis integration tests run and pass, test coverage exceeds all targets (84% total, 100% on security-sensitive models), static analysis is clean, and OpenAPI schema generation succeeds with zero warnings.

## Next stage allowed: YES

Stage 2 (Identity, Multi-Tenancy, and Authorization) is authorized to begin.
