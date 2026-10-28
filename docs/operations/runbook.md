# Production Operations Runbook

## 1. Overview & Service Objectives

This runbook guides on-call site reliability engineers and operators in managing, diagnosing, and maintaining the CMS Backend in production.

### Operational SLO Targets
- **API Availability:** 99.9% uptime per calendar month.
- **API Latency (p95):** < 150 ms for public content delivery, < 300 ms for authenticated management mutations.
- **Readiness Probe Target:** < 200 ms response time on `/health/ready`.

---

## 2. Common Alerts & Incident Triage

### Scenario A: Elevated HTTP 5xx Error Rates
1. **Locate Correlation IDs:**
   Inspect reverse proxy and application logs for `"request_id": "<uuid>"`.
   ```bash
   # Filter logs by error status and correlation ID
   cat /var/log/cms/app.log | jq 'select(.level=="ERROR" and .status>=500)'
   ```
2. **Database Health Check:**
   Verify database connectivity and query wait states:
   ```bash
   python manage.py check --database default
   ```
3. **Inspect Application Error Envelopes:**
   All unhandled exceptions emit the uniform error payload:
   ```json
   {
     "error": {
       "code": "internal_error",
       "message": "An unexpected error occurred.",
       "request_id": "8fa360e2-6352-446f-bca1-74400a4d1cf6"
     }
   }
   ```
   Cross-reference the `request_id` in centralized logging (Datadog/CloudWatch) to inspect full tracebacks without customer PII or token leakage.

---

### Scenario B: Celery Queue Backlog & Worker Lag
1. **Check Queue Depths:**
   ```bash
   celery -A cms inspect active
   celery -A cms inspect reserved
   ```
2. **Inspect Redis Queue Length:**
   ```bash
   redis-cli -u $REDIS_URL LLEN default
   redis-cli -u $REDIS_URL LLEN indexing
   redis-cli -u $REDIS_URL LLEN analytics
   ```
3. **Remediation:**
   - Scale Celery worker replicas horizontally:
     ```bash
     kubectl scale deployment/cms-worker --replicas=6
     ```
   - If workers are blocked on external provider outages (e.g. Google Search Console or Bing returning 503), verify tasks are backing off with exponential jitter. Provider rate limits (HTTP 429) automatically pause task retries with bounded caps.

---

### Scenario C: PostgreSQL Connection Pool Exhaustion
1. **Symptoms:**
   - Readiness probe `/health/ready` returns `HTTP 503 {"status": "degraded", "database": "unavailable"}`.
   - Logs show `django.db.utils.OperationalError: FATAL: remaining connection slots are reserved`.
2. **Diagnosis:**
   ```sql
   SELECT count(*), state FROM pg_stat_activity WHERE datname='cms_production' GROUP BY state;
   ```
3. **Remediation:**
   - Verify `POSTGRES_CONN_MAX_AGE` is set appropriately (60s default).
   - Ensure Gunicorn worker counts do not exceed `(2 * vCPU) + 1` per node.
   - Deploy PgBouncer or AWS RDS Proxy between web pods and PostgreSQL.

---

## 3. Maintenance Procedures & Key Rotation

### A. Envelope Encryption KEK (Master Key) Rotation
The CMS Backend uses two-tier envelope encryption for search provider credentials and OAuth tokens (per-record DEK encrypted by environment Master KEK via AES-256-GCM).

**Rotation Procedure:**
1. Generate a new 256-bit random key:
   ```bash
   openssl rand -hex 32
   ```
2. Configure the new key as `ENCRYPTION_MASTER_KEY` while retaining the prior key in `ENCRYPTION_FALLBACK_KEYS` (comma-separated):
   ```ini
   ENCRYPTION_MASTER_KEY=<new-64-hex-char-key>
   ENCRYPTION_FALLBACK_KEYS=<old-64-hex-char-key>
   ```
3. Run the re-encryption management command:
   ```bash
   python manage.py reencrypt_credentials
   ```
4. Verify all records decrypt cleanly under the new KEK.
5. Remove the old key from `ENCRYPTION_FALLBACK_KEYS` on the next release cycle.

---

### B. JWT Signing Key Rotation
1. The CMS Backend supports both symmetric HMAC keys and asymmetric RS256/EdDSA key pairs.
2. For RS256: Publish the new public key in the JWKS / configuration allowlist before promoting the new private key to active signing.
3. Token rotation automatically revokes the entire token family upon reuse detection, protecting compromised refresh tokens.

---

### C. Periodic Retention Pruning
Two automated Celery Beat jobs manage privacy data retention:
1. `cleanup_expired_consent_records`: Prunes visitor consent entries exceeding site `retention_days`.
2. `cleanup_expired_analytics_events`: Prunes first-party analytics events exceeding site event retention settings.

Manual execution if required:
```bash
python manage.py run_retention_cleanup --days 365
```
