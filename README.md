# Multi-Tenant Headless CMS Backend

A production-oriented, API-only headless CMS backend engineered with multi-tenant content management, technical SEO automation, search-engine discovery/indexing integrations (Google Search Console, Bing Webmaster Tools, IndexNow), Google Analytics 4 reporting, cookie consent management, and privacy-preserving visitor analytics.

---

## Architecture & Technology Stack

- **Runtime:** Python 3.13 (supported >= 3.12, < 3.14)
- **Framework:** Django 5.2 (Long Term Support) + Django REST Framework 3.18
- **Database:** PostgreSQL 16/17 (Strict multi-tenancy, JSONB schemas, transactional revisions)
- **Asynchronous Task Queue:** Celery 5.6 + Redis 7 (Isolated queues, rate-limited provider adapters, exponential backoff)
- **API Specification:** OpenAPI 3.0 via `drf-spectacular`
- **Containerization:** Multi-stage unprivileged Docker containers (`api`, `worker`, `beat`, `postgres`, `redis`)
- **Code Quality & Security:** Ruff, Mypy, Bandit (SAST), pip-audit (SCA), Gitleaks

---

## Project Structure

```text
├── apps/
│   ├── common/              # Errors, pagination, throttling, logging/redaction, health probes
│   ├── accounts/            # Custom User (UUID), authentication, token rotation, external issuer adapter
│   ├── tenancy/             # Workspaces, memberships, roles (Owner/Admin/Editor/Analyst), scoped querysets
│   ├── audit/               # Immutable audit events
│   ├── sites/               # Site registration, normalized domain handling, DNS TXT verification
│   ├── content/             # Schema-driven content types, draft/publish lifecycle, immutable revisions, public delivery
│   ├── seo/                 # Page/Site SEO, canonical validation, structured data, redirects, sitemaps, robots.txt, SEO audit
│   ├── search_integrations/ # GSC, Bing, IndexNow adapters, OAuth token encryption, durable indexing jobs
│   ├── analytics/           # GA4 property reporting, first-party allowlisted event ingestion
│   ├── consent/             # Per-site consent policy versions, visitor consent records, retention cleanup
│   └── github_integration/  # Feature-flagged GitHub App onboarding, detection, integration PR generation
├── cms/                     # Core settings (split base/dev/test/prod), WSGI, ASGI, URLs
├── docs/                    # Architecture, requirements matrix, threat model, test strategy, stage reports
├── requirements/            # Pinned, audited dependency manifests (base.txt, dev.txt)
├── tests/                   # Pytest suite (unit, API, PostgreSQL integration, security, contract)
├── docker-compose.yml       # Local dev & integration environment (Postgres 16, Redis 7, API)
└── Dockerfile               # Production container image
```

---

## Quick Start (Local Development)

### 1. Prerequisites
- Python 3.12 or 3.13 (`py -3.13` on Windows)
- Docker Desktop (with Docker Compose v2+)
- Git

### 2. Environment Setup
Copy the environment template:
```bash
cp .env.example .env
```

Create and activate the virtual environment:
```bash
# Windows
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1

# Linux / macOS
python3.13 -m venv .venv
source .venv/bin/activate
```

Install compiled dependencies:
```bash
pip install -r requirements/dev.txt -r requirements/base.txt
```

### 3. Start Infrastructure (PostgreSQL & Redis)
```bash
docker compose up -d postgres redis
```

### 4. Apply Database Migrations
```bash
python manage.py migrate
```

### 5. Run the Local Development Server
```bash
python manage.py runserver 127.0.0.1:8000
```

---

## Core Endpoints

- **Liveness Probe:** `GET /health/live` (Returns HTTP 200 `{"status": "live"}`)
- **Readiness Probe:** `GET /health/ready` (Verifies DB and Redis connectivity; returns HTTP 200 or 503)
- **OpenAPI 3 Schema:** `GET /api/v1/schema/`
- **Interactive Swagger UI:** `GET /api/v1/docs/` (Disabled in production by default)
- **Interactive ReDoc UI:** `GET /api/v1/redoc/`

---

---

## Documentation Index

### 1. Operations & Deployment
- [Production Deployment Guide](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/operations/deployment.md)
- [Production Operations Runbook](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/operations/runbook.md)
- [Backup, Disaster Recovery & Restore Guide](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/operations/backup-restore.md)
- [Production Release Checklist](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/operations/release-checklist.md)

### 2. Security & Privacy
- [Security Controls & Threat Model Closure](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/security/security-controls.md)
- [Privacy Architecture, Data Minimization & Retention](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/privacy/data-flow-and-retention.md)
- [System Threat Model](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/engineering/threat-model.md)
- [Risk Register](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/engineering/risk-register.md)

### 3. API Reference Guides
- [Authentication, Tenancy & RBAC API Reference](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/api/auth-and-tenancy.md)
- [Content Management & Public Delivery API Reference](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/api/content-api.md)
- [Technical SEO Engine API Reference](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/api/seo-api.md)
- [Consent & Analytics API Reference](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/api/consent-and-analytics-api.md)
- [External Search & GitHub Integrations API Reference](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/api/integrations-api.md)

### 4. Integrations
- [MarketIntel Federated Integration Guide](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/integrations/marketintel-integration.md)
- [GitHub App Integration Operational Guide](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/integrations/github-app-integration.md)
- [Search & Analytics Provider Specifications](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/integrations/provider-notes.md)

---

## Quality & Security Verification Suite

Run the full automated test suite with coverage:
```bash
pytest --cov=apps --cov-report=term-missing
```

Verify MarketIntel decoupling:
```bash
pytest tests/test_no_marketintel_coupling.py
```

Run code formatting and linting:
```bash
ruff format --check .
ruff check .
```

Run static type checking:
```bash
mypy apps
```

Run SAST security scan:
```bash
bandit -r apps -c pyproject.toml
```

Run dependency vulnerability audit:
```bash
pip-audit
```

Verify Django production deployment checks:
```bash
python manage.py check --deploy --settings=cms.settings.prod
```

Validate OpenAPI specification:
```bash
python manage.py spectacular --validate --fail-on-warn --file openapi.yaml
```

---

## Engineering Stage Reports

This service was constructed following the SDE workflow specified in `.agents/skills/sde-workflow/SKILL.md`. Each development phase progressed through small, verifiable stages with mandatory gates, security reviews, and traceable evidence:
- [Stage Reports Index](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/engineering/stage-reports/README.md)
- [Stage 00 — Discovery & Requirements](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/engineering/stage-reports/stage-00.md)
- [Stage 01 — Project Foundation](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/engineering/stage-reports/stage-01.md)
- [Stage 02 — Authentication, Tenancy & Audit](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/engineering/stage-reports/stage-02.md)
- [Stage 03 — Sites/Domains & Content Delivery](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/engineering/stage-reports/stage-03.md)
- [Stage 04 — Technical SEO Engine](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/engineering/stage-reports/stage-04.md)
- [Stage 05 — Search Provider Integrations](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/engineering/stage-reports/stage-05.md)
- [Stage 06 — Analytics & Privacy Event Ingestion](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/engineering/stage-reports/stage-06.md)
- [Stage 07 — Consent & Cookie Preference Backend](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/engineering/stage-reports/stage-07.md)
- [Stage 08 — GitHub Repository Onboarding & Integration PRs](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/engineering/stage-reports/stage-08.md)
- [Stage 09 — Production Hardening & Release Verification](file:///c:/Users/mohan/OneDrive/Desktop/CMS/docs/engineering/stage-reports/stage-09.md)

