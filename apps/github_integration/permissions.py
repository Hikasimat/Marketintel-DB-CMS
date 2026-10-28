"""Feature-flag permissions enforcing GITHUB_APP_ENABLED requirements (GH-7)."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request


class IsGitHubAppEnabled(permissions.BasePermission):
    """Enforces that GitHub App integration is enabled via configuration (GH-7)."""

    def has_permission(self, request: Request, view: Any) -> bool:
        enabled = getattr(settings, "GITHUB_APP_ENABLED", False)
        if not enabled:
            raise PermissionDenied(
                "GitHub App integration is disabled on this server. "
                "Enable GITHUB_APP_ENABLED=true in environment configuration."
            )
        return True
