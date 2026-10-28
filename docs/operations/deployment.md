# Production Deployment Guide

## Overview

The CMS Backend is a production-grade, API-only headless CMS engineered for deployment as a stateless containerized service backed by PostgreSQL 16+ and Redis 7+.

```
                     ┌────────────────────────┐
                     │ Cloudflare / CDN / TLS │
                     └───────────┬────────────┘
                                 │ HTTPS (443)
                     ┌───────────▼────────────┐
                     │ Reverse Proxy / Ingress│
                     │ (Nginx / AWS ALB)      │
                     └───────────┬────────────┘
                                 │ HTTP (8000)
             ┌───────────────────┴───────────────────┐
             │                                       │
   ┌─────────▼─────────┐                   ┌─────────▼─────────┐
   │ Gunicorn/Uvicorn  │                   │ Gunicorn/Uvicorn  │
   │ API Worker Node 1 │                   │ API Worker Node 2 │
   └─────────┬─────────┘                   └─────────┬─────────┘
             │                                       │
             ├───────────────────┬───────────────────┤
             │                   │                   │
   ┌─────────▼─────────┐   ┌─────▼───────┐   ┌───────▼────────┐
   │ PostgreSQL 16     │   │   Redis 7   │   │ Celery Workers │
   │ (Managed Primary) │   │ (Cache/MQ)  │   │  & Beat Node   │
   └───────────────────┘   └─────────────┘   └────────────────┘
```

---

## 1. Prerequisites & Resource Sizing

### Minimum Recommended Production Topology
- **API Web Service:** 2+ replicas, 1 vCPU, 2 GB RAM each.
- **Celery Worker:** 2+ replicas, 1 vCPU, 2 GB RAM each.
- **Celery Beat:** 1 replica (singleton), 0.5 vCPU, 512 MB RAM.
- **PostgreSQL Database:** Managed PostgreSQL 16 or 17 (e.g. AWS RDS Aurora PostgreSQL, GCP Cloud SQL), 2+ vCPUs, 4 GB RAM, Multi-AZ with read replica.
- **Redis Service:** Managed Redis 7+ cluster (e.g. AWS ElastiCache, GCP Memorystore), in-memory cache and message broker.

---

## 2. Environment Configuration

Production deployments must load settings via `cms.settings.prod`. The application enforces fail-fast startup validation on required environment variables:

| Variable | Description | Production Example / Requirement |
|----------|-------------|-----------------------------------|
| `DJANGO_SETTINGS_MODULE` | Active Django settings module | `cms.settings.prod` |
| `DJANGO_SECRET_KEY` | Cryptographic secret for signing | Min 50 characters, cryptographically random |
| `DJANGO_DEBUG` | Debug mode toggle | Strictly `false` in production |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated allowed HTTP Host headers | `api.cms.example.com` |
| `PUBLIC_BASE_URL` | Canonical public management base URL | `https://api.cms.example.com` |
| `PUBLIC_API_URL` | Public site delivery API endpoint | `https://api.cms.example.com` |
| `POSTGRES_DB` | Database name | `cms_production` |
| `POSTGRES_USER` | Database role | `cms_app` |
| `POSTGRES_PASSWORD` | Database password | Loaded from Secrets Manager |
| `POSTGRES_HOST` | Database host | `postgres-primary.internal` |
| `POSTGRES_PORT` | Database port | `5432` |
| `POSTGRES_SSLMODE` | PostgreSQL SSL mode | `require` or `verify-full` |
| `REDIS_URL` | Redis connection URI | `rediss://redis.internal:6379/0` (TLS) |
| `ENCRYPTION_MASTER_KEY` | Hex-encoded 256-bit AES Master Key (KEK) | 64 hex characters (e.g. from AWS KMS / HashiCorp Vault) |
| `TRUST_FORWARDED_PROTO` | Trust `X-Forwarded-Proto` header from proxy | `true` |
| `SECURE_SSL_REDIRECT` | Enforce HTTPS redirect on non-health routes | `true` |
| `SECURE_HSTS_SECONDS` | HTTP Strict Transport Security duration | `31536000` (1 year) |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | Include subdomains in HSTS | `true` |
| `SECURE_HSTS_PRELOAD` | Allow browser HSTS preload list submission | `true` |
| `CORS_ALLOWED_ORIGINS` | Management console origins allowlist | `https://admin.example.com` |
| `LOG_JSON` | Emit structured JSON log records to stdout | `true` |
| `GITHUB_APP_ENABLED` | Toggle GitHub App integration | `true` or `false` |

---

## 3. Container Execution

### Docker Image
The application uses a multi-stage Docker build producing an unprivileged, minimal runtime container.

```bash
# Build production image
docker build -t cms-backend:latest .

# Run container as unprivileged user (UID 1000)
docker run -d \
  --name cms-api \
  --env-file /etc/cms/production.env \
  -p 8000:8000 \
  cms-backend:latest
```

### Process Commands

1. **Web API Service (Gunicorn + Uvicorn Workers):**
   ```bash
   gunicorn cms.wsgi:application \
     --bind 0.0.0.0:8000 \
     --workers 4 \
     --worker-class uvicorn.workers.UvicornWorker \
     --max-requests 2000 \
     --max-requests-jitter 200 \
     --timeout 30 \
     --access-logfile - \
     --error-logfile -
   ```

2. **Celery Worker (Default & Priority Queues):**
   ```bash
   celery -A cms worker \
     --loglevel=INFO \
     --concurrency=4 \
     -Q default,indexing,analytics,maintenance \
     --prefetch-multiplier=1
   ```

3. **Celery Beat (Periodic Scheduler — Singleton):**
   ```bash
   celery -A cms beat \
     --loglevel=INFO \
     --scheduler django_celery_beat.schedulers:DatabaseScheduler
   ```

---

## 4. Health Probes & Load Balancer Integration

The backend exposes unauthenticated health endpoints exempted from HTTPS redirection:

- **Liveness Probe:** `GET /health/live`
  - Validates process responsiveness. Returns `HTTP 200 {"status": "ok"}`.
  - Used by Kubernetes / ECS to determine if the container should be restarted.
- **Readiness Probe:** `GET /health/ready`
  - Validates active connectivity to PostgreSQL and Redis without leaking internal network topologies.
  - Returns `HTTP 200 {"status": "ready"}` when all dependencies respond within timeout bounds.
  - Returns `HTTP 503 {"status": "degraded"}` if PostgreSQL or Redis is unreachable.
  - Used by load balancers to route traffic only to fully initialized instances.

---

## 5. Security & Reverse Proxy Configuration

When operating behind an ALB, Cloudflare, or Nginx:
1. Ensure the reverse proxy strips any client-supplied `X-Forwarded-Proto` and sets `X-Forwarded-Proto: https` on TLS connections.
2. Ensure the reverse proxy sets `X-Request-ID` or allows the backend to generate unique correlation UUIDs.
3. Keep `TRUST_FORWARDED_PROTO=true` so Django correctly inspects proxy headers while exempting `/health/` probes from redirect loops.
4. Verify deployment configuration via:
   ```bash
   python manage.py check --deploy --settings=cms.settings.prod
   ```
