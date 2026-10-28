# Dependency Inventory & Rationale

**Runtime Environment:** CPython 3.13 (supported >=3.12, <3.14).
**Target OS / Deployment:** Linux containers (Debian slim), verified on Windows/Linux host.

## Runtime Dependencies (`requirements/base.txt`)

| Package | Version | Purpose & Security / Compatibility Rationale |
|---------|---------|----------------------------------------------|
| `Django` | 5.2.18 | Primary web framework. 5.2 is the official Long Term Support (LTS) release, receiving security fixes through 2028. Provides robust ORM, database migrations, authentication hashing, and middleware. |
| `djangorestframework` | 3.18.3 | Core API toolkit. Provides serializers, viewsets, authentication and permissions model, request throttling, and custom exception handler capabilities. |
| `drf-spectacular` | 0.30.0 | OpenAPI 3.0+ schema generation and interactive documentation (Swagger / Redoc). Validates schema consistency without manual YAML/JSON synchronization. |
| `django-cors-headers` | 4.9.0 | CORS middleware for granular, origin-scoped cross-origin requests. Configured with strict origins and disallows credentials globally. |
| `psycopg` & `psycopg-binary` | 3.3.6 | Native PostgreSQL 3.x driver for Python. Supports JSONB, connection pooling, client-side parameters, and asynchronous queries. |
| `celery` | 5.6.3 | Distributed task queue for asynchronous background processing (search provider sync, sitemap rebuilds, webhook ingestion, data retention). |
| `redis` | 6.4.0 | High-performance client for Redis cache, rate-limit counters, and Celery message broker. |
| `gunicorn` | 23.0.0 | Production WSGI HTTP server for Unix containers, running multiple worker processes behind reverse proxies. |

## Development & CI Tooling (`requirements/dev.txt`)

| Package | Purpose |
|---------|---------|
| `pytest` | Test execution framework. |
| `pytest-django` | Django fixtures, database transactions, and client test helpers. |
| `pytest-cov` | Statement and branch code coverage measurement and threshold verification. |
| `ruff` | Fast Python linter and code formatter. Replaces flake8, isort, black, and bandit S rules. |
| `mypy` | Static type checker. |
| `django-stubs` & `djangorestframework-stubs` | Type annotations for Django ORM, querysets, and DRF serializers. |
| `bandit` | Static Application Security Testing (SAST) for common security anti-patterns. |
| `pip-audit` | Audits pinned dependencies against the Python Packaging Advisory Database for known vulnerabilities. |
