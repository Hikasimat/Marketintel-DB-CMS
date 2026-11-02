"""Test settings."""

from __future__ import annotations

import os

from .base import load

globals().update(load("test"))

if os.getenv("USE_SQLITE_TESTS", "1") == "1" and not os.getenv("DATABASE_URL"):
    DATABASES = {  # noqa: F405
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }

