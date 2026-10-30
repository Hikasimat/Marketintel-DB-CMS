"""Custom drf-spectacular hooks and filters."""

from __future__ import annotations

from typing import Any


def filter_duplicate_slash_endpoints(
    endpoints: list[tuple[str, str, str, Any]],
) -> list[tuple[str, str, str, Any]]:
    """Deduplicate endpoints where both /path and /path/ are registered.

    Avoids operationId collisions in OpenAPI schema generation.
    """
    seen: set[tuple[str, str]] = set()
    deduped: list[tuple[str, str, str, Any]] = []
    for path, path_regex, method, callback in endpoints:
        norm = path if path.endswith("/") else f"{path}/"
        key = (norm, method.upper())
        if key in seen:
            continue
        seen.add(key)
        deduped.append((path, path_regex, method, callback))
    return deduped
