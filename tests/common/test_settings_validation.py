"""Fail-fast settings validation tests (FND-1)."""

from __future__ import annotations

import pytest
from django.core.exceptions import ImproperlyConfigured

from cms.settings.base import load
from cms.settings.env import is_http_origin, is_redis_url


@pytest.mark.req("FND-1")
def test_dev_settings_load_with_defaults() -> None:
    settings = load("dev", environ={})
    assert settings["DEBUG"] is True
    assert "localhost" in settings["ALLOWED_HOSTS"]
    assert settings["SETTINGS_PROFILE"] == "dev"


@pytest.mark.req("FND-1")
def test_prod_fails_fast_with_all_missing_required_variables() -> None:
    with pytest.raises(ImproperlyConfigured) as exc_info:
        load("prod", environ={})

    msg = str(exc_info.value)
    # Check that required variables are reported
    assert "DJANGO_SECRET_KEY is required" in msg
    assert "DJANGO_ALLOWED_HOSTS is required" in msg
    assert "PUBLIC_BASE_URL is required" in msg
    assert "POSTGRES_DB is required" in msg
    assert "POSTGRES_USER is required" in msg
    assert "POSTGRES_PASSWORD is required" in msg
    assert "REDIS_URL is required" in msg


@pytest.mark.req("FND-1")
def test_prod_rejects_debug_true() -> None:
    valid_env = {
        "DJANGO_SECRET_KEY": "a" * 60,
        "DJANGO_ALLOWED_HOSTS": "api.example.com",
        "PUBLIC_BASE_URL": "https://api.example.com",
        "POSTGRES_DB": "cms",
        "POSTGRES_USER": "cms",
        "POSTGRES_PASSWORD": "secret_password_123",
        "REDIS_URL": "redis://redis:6379/0",
        "DJANGO_DEBUG": "true",
    }
    with pytest.raises(ImproperlyConfigured) as exc_info:
        load("prod", environ=valid_env)

    msg = str(exc_info.value)
    assert "DJANGO_DEBUG must not be true in production" in msg
    # Verify passwords/secrets are never printed in error message
    assert "secret_password_123" not in msg
    assert "a" * 60 not in msg


@pytest.mark.req("FND-1")
def test_prod_rejects_wildcard_allowed_hosts() -> None:
    env = {
        "DJANGO_SECRET_KEY": "b" * 60,
        "DJANGO_ALLOWED_HOSTS": "api.example.com,*",
        "PUBLIC_BASE_URL": "https://api.example.com",
        "POSTGRES_DB": "cms",
        "POSTGRES_USER": "cms",
        "POSTGRES_PASSWORD": "cms",
        "REDIS_URL": "redis://localhost:6379/0",
    }
    with pytest.raises(ImproperlyConfigured) as exc_info:
        load("prod", environ=env)

    assert "DJANGO_ALLOWED_HOSTS must not contain '*' in production" in str(exc_info.value)


@pytest.mark.req("FND-1")
def test_cors_origin_validator() -> None:
    assert is_http_origin("http://localhost:3000") is True
    assert is_http_origin("https://app.example.com") is True
    assert is_http_origin("https://app.example.com:8443") is True
    # Disallow path, query, fragment
    assert is_http_origin("https://app.example.com/api") is False
    assert is_http_origin("https://app.example.com?query=1") is False
    assert is_http_origin("ftp://example.com") is False


@pytest.mark.req("FND-1")
def test_redis_url_validator() -> None:
    assert is_redis_url("redis://localhost:6379/0") is True
    assert is_redis_url("rediss://secure-redis.cloud:6380/1") is True
    assert is_redis_url("http://localhost:6379") is False
    assert is_redis_url("invalid-url") is False
