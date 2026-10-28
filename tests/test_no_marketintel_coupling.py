"""Verifies independence from MarketIntel internal codebase (MI-2)."""

from __future__ import annotations

from pathlib import Path

import pytest

FORBIDDEN_TERMS = [
    "marketintel.models",
    "marketintel.db",
    "marketintel_db",
    "from marketintel",
    "import marketintel",
]


@pytest.mark.req("MI-2")
def test_no_marketintel_internal_imports_in_source() -> None:
    root = Path(__file__).resolve().parent.parent
    source_dirs = [root / "apps", root / "cms"]

    violations: list[str] = []
    for s_dir in source_dirs:
        for py_path in s_dir.rglob("*.py"):
            content = py_path.read_text(encoding="utf-8")
            for term in FORBIDDEN_TERMS:
                if term in content:
                    violations.append(f"{py_path}: contains '{term}'")

    assert not violations, "MarketIntel internal coupling detected:\n" + "\n".join(violations)
