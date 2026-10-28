# Production Release Checklist

## 1. Pre-Deployment Verification Gates (CI Pipeline)

Before any release candidate artifact is approved for staging or production deployment, all automated gates must pass:

- [ ] **Full Pytest Suite:** 100% of tests passing (`pytest tests/`).
- [ ] **Coverage Minimums:** $\ge 80\%$ overall statement coverage; $\ge 90\%$ on security-sensitive modules (`accounts`, `tenancy`, `consent`, `crypto`).
- [ ] **MarketIntel Decoupling Test:** Clean pass on `tests/test_no_marketintel_coupling.py`.
- [ ] **Static Type Checking:** Clean pass on `mypy apps` (0 errors).
- [ ] **Code Formatting & Linting:** Clean pass on `ruff format --check .` and `ruff check .`.
- [ ] **SAST Security Scan:** Clean pass on `bandit -r apps -c pyproject.toml` (0 High / Medium findings).
- [ ] **Software Supply Chain Audit:** Clean pass on `pip-audit` (0 known CVEs).
- [ ] **Secret Scan:** Clean pass on Gitleaks / automated log redaction regression tests.
- [ ] **OpenAPI Specification:** Clean pass on `python manage.py spectacular --validate --fail-on-warn --file openapi.yaml`.
- [ ] **Production Settings Check:** Clean pass on `python manage.py check --deploy --settings=cms.settings.prod` (0 issues).

---

## 2. Database Migration & Deployment Procedure

1. **Pre-flight Snapshot:** Trigger an automated PostgreSQL snapshot prior to executing migrations.
2. **Apply Database Migrations:**
   Run migrations as an isolated job before routing live traffic to the new container image:
   ```bash
   python manage.py migrate --noinput
   ```
3. **Zero-Downtime Migration Policy:**
   - Database migrations must be backwards-compatible (additive columns with defaults, nullable fields, non-blocking index creation).
   - Destructive column removals or table drops must follow the expand-and-contract pattern across consecutive releases.
4. **Deploy Container Nodes:**
   Deploy web API pods using a rolling update strategy (maximum 25% surge, 0% unavailable).
5. **Verify Worker Nodes:**
   Restart Celery worker and beat pods after the database migrations succeed.

---

## 3. Post-Deployment Smoke Verification

Run the following sanity checks against the active deployment:

1. **Health Probes:**
   - `curl -f https://api.cms.example.com/health/live` returns HTTP 200 `{"status": "ok"}`.
   - `curl -f https://api.cms.example.com/health/ready` returns HTTP 200 `{"status": "ready"}`.
2. **OpenAPI Schema Check:**
   - `curl -f https://api.cms.example.com/api/v1/schema/` returns valid YAML/JSON spec.
3. **Public Content Delivery:**
   - Query a known published article on a verified site: `GET /api/v1/public/sites/{site_slug}/articles/{article_slug}/`.
4. **Log Inspection:**
   - Verify application logs are emitting structured JSON with `request_id`.
   - Verify sensitive headers (`Authorization`, `Cookie`) and tokens are redacted (`[REDACTED]`).

---

## 4. Rollback Criteria & Procedure

### Abort Triggers
Immediately initiate rollback if any of the following occur within 15 minutes of deployment:
- 5xx error rate exceeds 0.5% over a 5-minute rolling window.
- Readiness probe `/health/ready` fails for > 1 minute on multiple nodes.
- Database connection pool spikes to > 90% capacity.

### Rollback Procedure
1. Revert container image to the prior stable release tag:
   ```bash
   kubectl rollout undo deployment/cms-api
   kubectl rollout undo deployment/cms-worker
   ```
2. If the release included backwards-compatible migrations, leave the database as-is.
3. If an emergency schema rollback is required, roll back to the target migration:
   ```bash
   python manage.py migrate <app_name> <target_migration_number>
   ```
