"""Production settings."""

from __future__ import annotations

from .base import load

globals().update(load("prod"))
