"""CMS package marker and Celery app initialization."""

from __future__ import annotations

from .celery import app as celery_app

__all__ = ("celery_app",)
