"""Validators for repository names, branch references, and manifest payloads."""

from __future__ import annotations

import re

from rest_framework.exceptions import ValidationError

REPO_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$")
BRANCH_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.\/]{1,100}$")
MAX_MANIFEST_SIZE_BYTES = 512_000  # 500 KB max (SEC-5, GH-3)


def validate_repo_full_name(value: str) -> None:
    """Validate GitHub repository full name (owner/repo)."""
    if (
        not isinstance(value, str)
        or not REPO_NAME_PATTERN.match(value)
        or ".." in value
        or value.startswith("/")
        or value.endswith("/")
    ):
        raise ValidationError(
            "Repository full name must be in the format 'owner/repo' containing only "
            "alphanumeric characters, hyphens, underscores, or dots."
        )


def validate_branch_name(value: str) -> None:
    """Validate git branch reference name."""
    if (
        not isinstance(value, str)
        or not BRANCH_NAME_PATTERN.match(value)
        or ".." in value
        or value.startswith("/")
        or value.endswith("/")
        or value.startswith("-")
        or value.endswith(".lock")
        or "@{" in value
        or any(char in value for char in ["~", "^", ":", "\\", "*", "?", "[", " "])
    ):
        raise ValidationError(
            "Branch name contains invalid characters. Must be 1-100 characters and cannot "
            "contain '..', spaces, or special git revision characters."
        )


def validate_manifest_path(path: str) -> None:
    """Validate file path against path traversal and null-byte injection (GH-3)."""
    if not isinstance(path, str) or not path.strip():
        raise ValidationError("File path cannot be empty.")
    if (
        "\x00" in path
        or ".." in path
        or path.startswith("/")
        or path.startswith("\\")
        or ":" in path
        or "\\" in path
    ):
        raise ValidationError("Hostile or invalid file path detected.")


def validate_manifest_size(content: str | bytes) -> None:
    """Enforce maximum manifest content size bound (GH-3, SEC-5)."""
    size = len(content.encode("utf-8") if isinstance(content, str) else content)
    if size > MAX_MANIFEST_SIZE_BYTES:
        raise ValidationError(
            f"Manifest size ({size} bytes) exceeds the maximum allowed limit of "
            f"{MAX_MANIFEST_SIZE_BYTES} bytes."
        )
