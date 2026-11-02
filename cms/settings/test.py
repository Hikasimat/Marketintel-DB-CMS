"""Test settings."""

from __future__ import annotations

import os

from .base import load

globals().update(load("test"))

if os.getenv("USE_SQLITE_TESTS", "1") == "1" and not os.getenv("DATABASE_URL"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }

# Disable throttling during test suite execution to prevent cross-test interference
rest_framework_settings = globals().get("REST_FRAMEWORK", {})
rest_framework_settings["DEFAULT_THROTTLE_CLASSES"] = []
rest_framework_settings["DEFAULT_THROTTLE_RATES"] = {
    "anon": "100000/day",
    "user": "100000/day",
}
globals()["REST_FRAMEWORK"] = rest_framework_settings
