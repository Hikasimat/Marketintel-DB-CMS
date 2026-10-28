# Test Strategy

## 1. Principles

- Tests ship in the **same stage** as the code they cover. Meaningful tests are never weakened, skipped, or xfailed without a documented blocker.
- **PostgreSQL is the test database** for the integration suite. SQLite is not used: constraints, JSONB, partial indexes, and row locks must behave as they will in production.
- External providers are **never called in the default suite**. HTTP is mocked at the transport level (respx), and network access is blocked in tests (a socket guard fixture). Live checks are opt-in via `pytest -m live` and only run when the `LIVE_*` credentials are set. Results are reported as `LIVE-PASS`, `MOCK-PASS`, or `BLOCKED`.
- Every requirement ID in the [requirements matrix](requirements-matrix.md) maps to at least one test. Test docstrings or markers reference the ID (e.g. `@pytest.mark.req("CT-6")`), and a Stage 9 script verifies coverage of requirement IDs.

## 2. Test layers

| Layer | Tooling | Scope | Runs in |
|-------|---------|-------|---------|
| Unit | pytest | validators, normalizers, schema DSL, canonical/redirect logic, sitemap builder, consent decisions, crypto, retry policy, error mapping | every commit |
| API | DRF `APIClient`, pytest-django | status codes, error envelope, auth/permission, pagination, filters, throttles, OpenAPI conformance | every commit |
| DB integration | real PostgreSQL | constraints, transactions, concurrent publish (threads + `select_for_update`), job dedupe, migrations | every commit (CI service container) |
| Authorization matrix | parametrized pytest over (role × endpoint × action) and (tenant A user × tenant B object) | TEN-2, TEN-3 | every commit |
| Provider contract | respx fixtures built from documented request/response shapes (sources in `provider-notes.md`) | request shape, auth headers, error mapping 401/403/429/5xx/timeout/malformed | every commit |
| Security | dedicated `tests/security/` | SSRF, IDOR, XSS-safe serialization, open redirect, secret leakage in logs/responses, CORS, resource bounds | every commit |
| Migration | `manage.py migrate` on empty DB; `makemigrations --check`; upgrade-from-previous test (migrate to N-1 then N) | schema drift | every commit |
| Smoke | `docker compose up` + scripted HTTP flow (`scripts/smoke.py`) | end-to-end golden path + log secret scan | stage gates, CI on main |
| Performance/reliability | `django_assert_max_num_queries`, throttle tests, outage simulation with respx, light load test (locust or k6) on public delivery | N+1, caps, backpressure | Stage 3+, Stage 9 |
| Live (opt-in) | `-m live` | real provider sandbox/test properties | only when credentials are configured |

## 3. Fixtures and data

- factory-boy factories per model; `tenant_pair` fixture yields two fully populated workspaces (users of every role, sites, entries, connections, jobs, consent records) for IDOR tests.
- `fake_providers` fixture swaps adapters through the provider registry.
- Log capture fixture with a `assert_no_secrets(records)` helper that looks for known token/secret patterns and for the actual secret values used in the test.
- A frozen clock (time-machine) for expiry, retention, and backoff tests.

## 4. Static and supply-chain checks

| Check | Command (planned) | Gate |
|-------|------------------|------|
| Format | `ruff format --check .` | must pass |
| Lint | `ruff check .` | must pass |
| Types | `mypy apps/common apps/accounts apps/tenancy` (expanding per stage) | must pass on configured modules |
| SAST | `bandit -r apps -c pyproject.toml` | no unresolved medium+ findings |
| Dependencies | `pip-audit -r requirements/lock.txt` | no unresolved known vulns, or a triaged exception |
| Secrets | `gitleaks detect --no-banner` (or `detect-secrets` if gitleaks is unavailable locally) | clean |
| Django | `DJANGO_SETTINGS_MODULE=cms.settings.prod python manage.py check --deploy` (with placeholder-safe env) | clean or justified |
| Migrations | `python manage.py makemigrations --check --dry-run` | no drift |
| OpenAPI | `python manage.py spectacular --validate --fail-on-warn --file openapi.yaml` | must pass |
| Coverage | `pytest --cov=apps --cov-report=term-missing --cov-fail-under=80` + per-module threshold script | ≥80% overall, ≥90% security-sensitive |

## 5. Coverage targets

- Overall statement coverage ≥ 80%.
- ≥ 90% for `accounts`, `tenancy`, `common.crypto`, OAuth modules in `search_integrations`/`analytics`, `consent`, `common.net`.
- Coverage never substitutes for the scenario lists in the skill's quality matrix.

## 6. Stage gate evidence

Each stage report (`stage-reports/stage-XX.md`) records:
- exact commands and actual pass/fail/skip counts,
- coverage totals and per-sensitive-module numbers,
- static/security tool results and triage,
- external checks marked `LIVE-PASS` / `MOCK-PASS` / `BLOCKED`,
- review findings and their remediation.

## 7. Environment

- Local: Docker Desktop runs `postgres` and `redis` through `docker compose`. Python venv on 3.12/3.13 (decided in Stage 1).
- CI: GitHub Actions with Postgres + Redis service containers (workflow authored in Stage 1; it executes only once a remote exists, and local runs are the evidence until then).
- Windows host note: commands are documented for PowerShell and POSIX shells. CI runs Linux.
