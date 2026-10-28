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

## Quality & Security Test Suite

Run the full automated test suite:
```bash
pytest --cov=apps --cov=cms --cov-report=term-missing
```

Run code formatting and linting:
```bash
ruff format --check .
ruff check .
```

Run static type checking:
```bash
mypy apps/common apps/accounts
```

Run SAST security scan:
```bash
bandit -r apps -c pyproject.toml
```

Run dependency vulnerability audit:
```bash
pip-audit -r requirements/base.txt
```

Verify Django production deployment checks:
```bash
DJANGO_SETTINGS_MODULE=cms.settings.prod python manage.py check --deploy
```

---

## Development Engineering Workflow

This service is developed following the rigorous SDE workflow specified in `.agents/skills/sde-workflow/SKILL.md`. Each development phase progresses through small, verifiable stages with mandatory gates, security reviews, and traceable evidence.
Refer to `docs/engineering/stage-reports/` for detailed stage completion reports.
