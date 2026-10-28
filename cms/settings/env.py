"""Environment variable reading with fail-fast, value-safe validation (FND-1).

All problems are collected and reported together. Error messages contain
variable *names* and the nature of the problem only, never the values, so
secrets cannot leak into logs or crash output.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

_Str = str
_Bool = bool
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}


class _Required:
    def __repr__(self) -> str:
        return "REQUIRED"


#: Pass as ``default`` to make a variable mandatory.
REQUIRED: object = _Required()
_MISSING = REQUIRED


class Env:
    """Collects configuration errors instead of failing on the first one."""

    def __init__(self, environ: Mapping[_Str, _Str] | None = None) -> None:
        self._environ = os.environ if environ is None else environ
        self.errors: list[_Str] = []

    def _raw(self, name: _Str) -> _Str | None:
        value = self._environ.get(name)
        if value is None:
            return None
        value = value.strip()
        return value if value != "" else None

    def str(
        self,
        name: _Str,
        default: _Str | object | None = _MISSING,
        *,
        min_length: int = 0,
        validator: Callable[[_Str], _Bool] | None = None,
        problem: _Str = "has an invalid format",
    ) -> _Str:
        raw = self._raw(name)
        if raw is None:
            if default is _MISSING:
                self.errors.append(f"{name} is required but not set")
                return ""
            return default  # type: ignore[return-value]
        if len(raw) < min_length:
            self.errors.append(f"{name} must be at least {min_length} characters")
        elif validator is not None and not validator(raw):
            self.errors.append(f"{name} {problem}")
        return raw

    def bool(self, name: _Str, default: bool) -> bool:
        raw = self._environ.get(name)
        if raw is None:
            return default
        lowered = raw.strip().lower()
        if lowered in _TRUE:
            return True
        if lowered in _FALSE:
            return False
        self.errors.append(f"{name} must be a boolean (true/false)")
        return default

    def int(
        self,
        name: _Str,
        default: int,
        *,
        min_value: int | None = None,
        max_value: int | None = None,
    ) -> int:
        raw = self._raw(name)
        if raw is None:
            return default
        try:
            value = int(raw)
        except ValueError:
            self.errors.append(f"{name} must be an integer")
            return default
        if (min_value is not None and value < min_value) or (
            max_value is not None and value > max_value
        ):
            self.errors.append(f"{name} is out of the allowed range")
            return default
        return value

    def list(
        self,
        name: _Str,
        default: list[_Str] | None = None,
        *,
        item_validator: Callable[[_Str], _Bool] | None = None,
        problem: _Str = "contains an invalid item",
    ) -> list[_Str]:
        raw = self._raw(name)
        if raw is None:
            return list(default or [])
        items = [item.strip() for item in raw.split(",") if item.strip()]
        if item_validator is not None and not all(item_validator(i) for i in items):
            self.errors.append(f"{name} {problem}")
        return items

    def raise_if_errors(self) -> None:
        if self.errors:
            joined = "\n  - ".join(self.errors)
            raise ImproperlyConfigured(f"Invalid configuration:\n  - {joined}")


def is_http_origin(value: str) -> bool:
    """True for scheme://host[:port] with no path, query, or fragment."""
    parts = urlsplit(value)
    return (
        parts.scheme in {"http", "https"}
        and bool(parts.hostname)
        and parts.path in {"", "/"}
        and not parts.query
        and not parts.fragment
        and parts.username is None
    )


def is_redis_url(value: str) -> bool:
    parts = urlsplit(value)
    return parts.scheme in {"redis", "rediss"} and bool(parts.hostname)


def is_absolute_https_or_http_url(value: str) -> bool:
    parts = urlsplit(value)
    return parts.scheme in {"http", "https"} and bool(parts.hostname)
