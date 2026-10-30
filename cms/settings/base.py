"""Settings builder shared by all profiles (dev, test, prod).

Profiles call :func:`load` and publish the returned mapping into their module
namespace. Building settings in a function keeps validation testable with a
fake environment (see tests/common/test_settings_validation.py).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .env import REQUIRED, Env, is_absolute_https_or_http_url, is_http_origin, is_redis_url

BASE_DIR = Path(__file__).resolve().parent.parent.parent

PROFILES = {"dev", "test", "prod"}

# Insecure, clearly-labelled key used only in dev/test when none is provided.
_DEV_ONLY_SECRET_KEY = "dev-only-insecure-secret-key-do-not-use-in-production-0123456789"  # noqa: S105


def _load_env_string(content: str) -> None:
    """Load key-value pairs from an env-formatted string into os.environ."""
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            if (val.startswith('"') and val.endswith('"')) or (
                val.startswith("'") and val.endswith("'")
            ):
                val = val[1:-1]
            os.environ.setdefault(key, val)


def _load_dotenv(path: Path) -> None:
    """Load key-value pairs from a .env file into os.environ if not already set."""
    if not path.is_file():
        return
    try:
        with path.open("r", encoding="utf-8") as f:
            _load_env_string(f.read())
    except (OSError, UnicodeDecodeError):
        pass


def load(profile: str, environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    if profile not in PROFILES:
        raise ValueError(f"unknown settings profile: {profile}")
    is_prod = profile == "prod"
    is_test = profile == "test"
    if environ is None and not is_test:
        app_env_config = os.environ.get("APP_ENV_CONFIG")
        if app_env_config:
            _load_env_string(app_env_config)
        _load_dotenv(BASE_DIR / ".env")
        _load_dotenv(Path("/app/.env"))
    env = Env(os.environ if environ is None else environ)

    # --- Core -------------------------------------------------------------
    if is_prod:
        secret_key = env.str("DJANGO_SECRET_KEY", min_length=50)
    else:
        secret_key = env.str("DJANGO_SECRET_KEY", _DEV_ONLY_SECRET_KEY)
    debug = False if is_prod else env.bool("DJANGO_DEBUG", default=profile == "dev")
    if is_prod and env.bool("DJANGO_DEBUG", default=False):
        env.errors.append("DJANGO_DEBUG must not be true in production")

    allowed_hosts = env.list(
        "DJANGO_ALLOWED_HOSTS",
        default=[] if is_prod else ["localhost", "127.0.0.1", "testserver", ".trycloudflare.com"],
    )
    if is_prod and not allowed_hosts:
        env.errors.append("DJANGO_ALLOWED_HOSTS is required in production")
    if is_prod and "*" in allowed_hosts:
        env.errors.append("DJANGO_ALLOWED_HOSTS must not contain '*' in production")
    if is_prod:
        import socket

        try:
            container_ip = socket.gethostbyname(socket.gethostname())
            if container_ip not in allowed_hosts:
                allowed_hosts.append(container_ip)
            allowed_hosts.extend([".compute.internal", ".elb.amazonaws.com"])
        except Exception:  # noqa: S110
            pass

    public_base_url = env.str(
        "PUBLIC_BASE_URL",
        REQUIRED if is_prod else "http://localhost:8000",
        validator=is_absolute_https_or_http_url,
        problem="must be an absolute http(s) URL",
    )

    # --- Database (PostgreSQL only) --------------------------------------
    from urllib.parse import unquote, urlsplit

    database_url = env.str("DATABASE_URL", default=None)
    if database_url:
        parsed_db = urlsplit(database_url)
        db_user = unquote(parsed_db.username) if parsed_db.username else "cms"
        db_password = unquote(parsed_db.password) if parsed_db.password else "cms"
        db_host = parsed_db.hostname or "localhost"
        db_port = parsed_db.port or (5432 if is_prod else 55432)
        db_name = parsed_db.path.lstrip("/") or "postgres"
    else:
        db_name = env.str("POSTGRES_DB", REQUIRED if is_prod else "cms")
        db_user = env.str("POSTGRES_USER", REQUIRED if is_prod else "cms")
        db_password = env.str("POSTGRES_PASSWORD", REQUIRED if is_prod else "cms")
        db_host = env.str("POSTGRES_HOST", "localhost")
        db_port = env.int(
            "POSTGRES_PORT", 55432 if not is_prod else 5432, min_value=1, max_value=65535
        )

    db_conn_max_age = env.int("POSTGRES_CONN_MAX_AGE", 60, min_value=0, max_value=3600)
    db_schema = env.str("POSTGRES_SCHEMA", "cms" if is_prod else "public")
    db_sslmode = env.str(
        "POSTGRES_SSLMODE",
        "require" if is_prod else "prefer",
        validator=lambda v: (
            v in {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}
        ),
        problem="is not a valid libpq sslmode",
    )

    # --- Redis / Celery --------------------------------------------------
    redis_url = env.str(
        "REDIS_URL",
        REQUIRED if is_prod else None,
        validator=is_redis_url,
        problem="must be a redis:// or rediss:// URL",
    )

    # --- HTTP / security -------------------------------------------------
    cors_origins = env.list(
        "CORS_ALLOWED_ORIGINS",
        default=[],
        item_validator=is_http_origin,
        problem="must be a comma-separated list of scheme://host[:port] origins",
    )
    csrf_trusted_origins = env.list(
        "CSRF_TRUSTED_ORIGINS",
        default=[]
        if is_prod
        else ["http://localhost:8000", "http://127.0.0.1:8000", "https://*.trycloudflare.com"],
        item_validator=is_http_origin,
        problem="must be a comma-separated list of scheme://host[:port] origins",
    )
    trust_forwarded_proto = env.bool("TRUST_X_FORWARDED_PROTO", default=False)
    ssl_redirect = env.bool("SECURE_SSL_REDIRECT", default=is_prod)
    hsts_seconds = env.int("SECURE_HSTS_SECONDS", 31536000 if is_prod else 0, min_value=0)
    api_docs_enabled = env.bool("API_DOCS_ENABLED", default=not is_prod)
    admin_enabled = env.bool("ADMIN_ENABLED", default=False)
    log_level = env.str(
        "LOG_LEVEL",
        "INFO",
        validator=lambda v: v.upper() in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"},
        problem="must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL",
    ).upper()
    log_json = env.bool("LOG_JSON", default=is_prod)

    throttle_anon = env.str(
        "THROTTLE_ANON_RATE",
        "60/min",
        validator=_is_rate,
        problem="must look like '<n>/<sec|min|hour|day>'",
    )
    throttle_user = env.str(
        "THROTTLE_USER_RATE",
        "600/min",
        validator=_is_rate,
        problem="must look like '<n>/<sec|min|hour|day>'",
    )

    env.raise_if_errors()

    # --- Assemble ---------------------------------------------------------
    installed_apps = [
        "django.contrib.contenttypes",
        "django.contrib.auth",
        "django.contrib.sessions",
        "django.contrib.messages",
        "django.contrib.staticfiles",
        "corsheaders",
        "rest_framework",
        "drf_spectacular",
        "apps.common",
        "apps.accounts",
        "apps.audit",
        "apps.tenancy",
        "apps.sites",
        "apps.content",
        "apps.seo",
        "apps.integrations",
        "apps.analytics",
        "apps.consent",
    ]
    if admin_enabled:
        installed_apps.insert(0, "django.contrib.admin")

    middleware = [
        "apps.common.middleware.RequestIDMiddleware",
        "django.middleware.security.SecurityMiddleware",
        "corsheaders.middleware.CorsMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
        "apps.common.middleware.AccessLogMiddleware",
    ]

    if redis_url and "localhost" not in redis_url and "127.0.0.1" not in redis_url and not is_test:
        caches: dict[str, Any] = {
            "default": {
                "BACKEND": "django.core.cache.backends.redis.RedisCache",
                "LOCATION": redis_url,
                "TIMEOUT": 300,
            }
        }
    else:
        caches = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

    settings: dict[str, Any] = {
        "BASE_DIR": BASE_DIR,
        "SETTINGS_PROFILE": profile,
        "SECRET_KEY": secret_key,
        "DEBUG": debug,
        "ALLOWED_HOSTS": allowed_hosts,
        "PUBLIC_BASE_URL": public_base_url,
        "INSTALLED_APPS": installed_apps,
        "MIDDLEWARE": middleware,
        "ROOT_URLCONF": "cms.urls",
        "WSGI_APPLICATION": "cms.wsgi.application",
        "ASGI_APPLICATION": "cms.asgi.application",
        "ADMIN_ENABLED": admin_enabled,
        "API_DOCS_ENABLED": api_docs_enabled,
        "TEMPLATES": [
            {
                "BACKEND": "django.template.backends.django.DjangoTemplates",
                "DIRS": [],
                "APP_DIRS": True,
                "OPTIONS": {
                    "context_processors": [
                        "django.template.context_processors.request",
                        "django.contrib.auth.context_processors.auth",
                        "django.contrib.messages.context_processors.messages",
                    ]
                },
            }
        ],
        "DATABASES": {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": db_name,
                "USER": db_user,
                "PASSWORD": db_password,
                "HOST": db_host,
                "PORT": str(db_port),
                "CONN_MAX_AGE": 0 if is_test else db_conn_max_age,
                "CONN_HEALTH_CHECKS": True,
                "OPTIONS": {
                    "sslmode": db_sslmode,
                    "connect_timeout": 5,
                    **(
                        {"options": f"-c search_path={db_schema},public"}
                        if db_schema and db_schema != "public"
                        else {}
                    ),
                },
                "ATOMIC_REQUESTS": False,
            }
        },
        "DEFAULT_AUTO_FIELD": "django.db.models.BigAutoField",
        "AUTH_USER_MODEL": "accounts.User",
        "AUTH_PASSWORD_VALIDATORS": [
            {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
            {
                "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
                "OPTIONS": {"min_length": 12},
            },
            {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
            {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
            {"NAME": "apps.accounts.validators.PasswordComplexityValidator"},
        ],
        "LANGUAGE_CODE": "en-us",
        "TIME_ZONE": "UTC",
        "USE_I18N": True,
        "USE_TZ": True,
        "STATIC_URL": "static/",
        "STATIC_ROOT": BASE_DIR / "staticfiles",
        "CACHES": caches,
        "REDIS_URL": redis_url,
        # Request size bound (SEC-5). Per-endpoint limits are tighter where needed.
        "DATA_UPLOAD_MAX_MEMORY_SIZE": 1_048_576,
        "DATA_UPLOAD_MAX_NUMBER_FIELDS": 1000,
        "FILE_UPLOAD_MAX_MEMORY_SIZE": 1_048_576,
        # --- Authentication & JWT ---
        "JWT_SECRET_KEY": secret_key,
        "JWT_ACCESS_EXPIRATION_SECONDS": 900,
        "JWT_REFRESH_EXPIRATION_SECONDS": 604800,
        "JWT_ISSUER": "cms-backend",
        "JWT_AUDIENCE": "cms-api",
        "EXTERNAL_AUTH_ISSUERS": {},
        # --- DRF ---
        "REST_FRAMEWORK": {
            "DEFAULT_AUTHENTICATION_CLASSES": [
                "apps.accounts.auth_backends.JWTAuthentication",
                "apps.accounts.auth_backends.ExternalIssuerAuthentication",
            ],
            # Secure default: every endpoint requires auth unless it opts out explicitly.
            "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
            "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
            "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
            "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.DefaultPagination",
            "PAGE_SIZE": 25,
            "DEFAULT_THROTTLE_CLASSES": [
                "rest_framework.throttling.AnonRateThrottle",
                "rest_framework.throttling.UserRateThrottle",
            ],
            "DEFAULT_THROTTLE_RATES": {"anon": throttle_anon, "user": throttle_user},
            "EXCEPTION_HANDLER": "apps.common.errors.exception_handler",
            "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
            "UNAUTHENTICATED_USER": "django.contrib.auth.models.AnonymousUser",
            "TEST_REQUEST_DEFAULT_FORMAT": "json",
        },
        "SPECTACULAR_SETTINGS": {
            "TITLE": "Headless CMS API",
            "DESCRIPTION": "Standalone, API-only multi-tenant headless CMS backend.",
            "VERSION": "1.0.0",
            "SERVE_INCLUDE_SCHEMA": False,
            "SCHEMA_PATH_PREFIX": r"/api/v1",
            "PREPROCESSING_HOOKS": ["apps.common.spectacular.filter_duplicate_slash_endpoints"],
            "COMPONENT_SPLIT_REQUEST": True,
            "ENUM_NAME_OVERRIDES": {
                "ArticleStatusEnum": "apps.content.models.ArticleStatus",
                "ConnectionStatusEnum": "apps.integrations.models.ConnectionStatus",
                "SubmissionStatusEnum": "apps.integrations.models.SubmissionStatus",
                "AnalyticsEventTypeEnum": "apps.analytics.models.EventType",
                "AnalyticsDeviceCategoryEnum": "apps.analytics.models.DeviceCategory",
                "ConsentRecordStatusEnum": "apps.consent.models.ConsentRecordStatus",
                "ConsentTypeEnum": "apps.consent.models.ConsentType",
                "JurisdictionModeEnum": "apps.consent.models.JurisdictionMode",
                "GCMStateEnum": "apps.consent.models.GCMState",
            },
        },
        # --- CORS (never used as authentication; SEC-2) ---
        "CORS_ALLOWED_ORIGINS": cors_origins,
        "CORS_ALLOW_ALL_ORIGINS": not is_prod,
        "CORS_ALLOW_CREDENTIALS": False,
        "CORS_URLS_REGEX": r"^.*$",
        # --- Security headers ---
        "SECURE_CONTENT_TYPE_NOSNIFF": True,
        "SECURE_REFERRER_POLICY": "same-origin",
        "SECURE_CROSS_ORIGIN_OPENER_POLICY": "same-origin",
        "X_FRAME_OPTIONS": "DENY",
        "SECURE_SSL_REDIRECT": ssl_redirect,
        "SECURE_REDIRECT_EXEMPT": [r"^api/v1/health/", r"^health/"],
        "SECURE_HSTS_SECONDS": hsts_seconds,
        "SECURE_HSTS_INCLUDE_SUBDOMAINS": hsts_seconds > 0,
        "SECURE_HSTS_PRELOAD": env.bool("SECURE_HSTS_PRELOAD", default=is_prod),
        "SESSION_COOKIE_SECURE": is_prod,
        "SESSION_COOKIE_HTTPONLY": True,
        "CSRF_COOKIE_SECURE": is_prod,
        "CSRF_TRUSTED_ORIGINS": csrf_trusted_origins,
        "SECURE_PROXY_SSL_HEADER": ("HTTP_X_FORWARDED_PROTO", "https")
        if trust_forwarded_proto
        else None,
        "IS_TEST": is_test,
        # --- Celery ---
        "CELERY_BROKER_URL": redis_url or "memory://",
        "CELERY_RESULT_BACKEND": None,
        "CELERY_TASK_ALWAYS_EAGER": is_test,
        "CELERY_TASK_EAGER_PROPAGATES": is_test,
        "CELERY_TASK_ACKS_LATE": True,
        "CELERY_TASK_REJECT_ON_WORKER_LOST": True,
        "CELERY_WORKER_PREFETCH_MULTIPLIER": 1,
        "CELERY_TASK_TIME_LIMIT": 300,
        "CELERY_TASK_SOFT_TIME_LIMIT": 240,
        "CELERY_TASK_DEFAULT_QUEUE": "default",
        "CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP": True,
        # --- Logging ---
        "LOGGING": _logging_config(log_level, log_json),
    }
    return settings


def _is_rate(value: str) -> bool:
    try:
        count, period = value.split("/")
        return int(count) > 0 and period in {"s", "sec", "m", "min", "h", "hour", "d", "day"}
    except ValueError:
        return False


def _logging_config(level: str, as_json: bool) -> dict[str, Any]:
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request_context": {"()": "apps.common.logging.RequestContextFilter"},
        },
        "formatters": {
            "json": {"()": "apps.common.logging.JSONFormatter"},
            "console": {"()": "apps.common.logging.RedactingConsoleFormatter"},
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "json" if as_json else "console",
                "filters": ["request_context"],
            }
        },
        "root": {"handlers": ["default"], "level": level},
        "loggers": {
            "django": {"handlers": ["default"], "level": level, "propagate": False},
            # Django's own request logger duplicates our access log and may include
            # full request reprs; keep only errors.
            "django.request": {"handlers": ["default"], "level": "ERROR", "propagate": False},
            "django.server": {"handlers": ["default"], "level": "WARNING", "propagate": False},
            "apps": {"handlers": ["default"], "level": level, "propagate": False},
            "celery": {"handlers": ["default"], "level": level, "propagate": False},
        },
    }
