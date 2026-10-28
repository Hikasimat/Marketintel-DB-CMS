"""Validators for consent categories, visitor identifiers, and policy versions."""

from __future__ import annotations

import re
from typing import Any

from rest_framework.exceptions import ValidationError

VISITOR_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]{8,128}$")
POLICY_VERSION_PATTERN = re.compile(r"^[a-zA-Z0-9_\.\-]{1,50}$")
CATEGORY_KEY_PATTERN = re.compile(r"^[a-z0-9_]{2,30}$")


def validate_visitor_id(value: str) -> None:
    """Validate opaque pseudonymous visitor identifier (CON-3, ANA-5)."""
    if not isinstance(value, str) or not VISITOR_ID_PATTERN.match(value):
        raise ValidationError(
            "visitor_id must be an opaque string between 8 and 128 characters "
            "containing only alphanumeric characters, underscores, hyphens, or dots."
        )


def validate_policy_version_string(value: str) -> None:
    """Validate policy version string format (e.g. '1.0', '2026.1')."""
    if not isinstance(value, str) or not POLICY_VERSION_PATTERN.match(value):
        raise ValidationError(
            "Policy version must be between 1 and 50 characters containing only "
            "alphanumeric characters, dots, underscores, or hyphens."
        )


def validate_categories_payload(
    categories: Any,
    allowed_categories: dict[str, Any],
) -> dict[str, bool]:
    """Validate visitor submitted category choices (CON-3, CON-5).

    - Must be a dictionary.
    - All values must be booleans.
    - 'necessary' must be present and True.
    - Unknown categories are rejected.
    """
    if not isinstance(categories, dict):
        raise ValidationError(
            {
                "categories": (
                    "categories must be a JSON dictionary of category names to boolean values."
                )
            }
        )

    cleaned: dict[str, bool] = {}
    for key, val in categories.items():
        if not isinstance(key, str):
            raise ValidationError({"categories": "Category keys must be strings."})
        if not isinstance(val, bool):
            raise ValidationError(
                {"categories": f"Category value for '{key}' must be a boolean (true/false)."}
            )
        if key not in allowed_categories:
            raise ValidationError(
                {
                    "categories": (
                        f"Unrecognized category '{key}'. "
                        f"Allowed categories: {list(allowed_categories.keys())}"
                    )
                }
            )
        cleaned[key] = val

    if cleaned.get("necessary") is not True:
        raise ValidationError(
            {"categories": "The 'necessary' category is required and must be set to true."}
        )

    # Ensure all allowed categories have an explicit decision; if missing, default to False (CON-5)
    for cat_name, cat_meta in allowed_categories.items():
        if cat_name not in cleaned:
            cleaned[cat_name] = bool(cat_meta.get("default_state", False))

    return cleaned


def validate_custom_categories_definition(custom_cats: Any) -> None:
    """Validate custom category definitions added by site admins (CON-1, CON-5)."""
    if not isinstance(custom_cats, dict):
        raise ValidationError("Custom categories must be a dictionary.")

    for key, spec in custom_cats.items():
        if not CATEGORY_KEY_PATTERN.match(key):
            raise ValidationError(
                f"Category key '{key}' is invalid. Must be 2-30 characters of lower snake_case."
            )
        if key in ("necessary", "analytics", "marketing", "preferences"):
            raise ValidationError(
                f"Category '{key}' is a built-in category and cannot be redefined."
            )
        if not isinstance(spec, dict):
            raise ValidationError(f"Category specification for '{key}' must be a dictionary.")
        title = spec.get("title")
        if not title or not isinstance(title, str) or len(title) > 100:
            raise ValidationError(f"Category '{key}' requires a title string up to 100 characters.")
