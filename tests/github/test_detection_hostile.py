"""Tests for safe manifest parsing, framework detection, and hostile input defense (GH-3)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from rest_framework.exceptions import ValidationError

from apps.github_integration.analyzer import analyze_repository_manifests
from apps.github_integration.models import DetectedFramework


def test_framework_detection_supported_frameworks():
    """Verify safe detection for Next.js, Vite/React, Astro, Nuxt, and Remix."""
    # 1. Next.js
    next_files = {
        "package.json": (
            '{"name": "my-next-app", "dependencies": {"next": "15.0.0", "react": "19.0.0"}}'
        ),
        "next.config.mjs": "export default {};",
    }
    res_next = analyze_repository_manifests(next_files)
    assert res_next["detected_framework"] == DetectedFramework.NEXT_JS
    assert res_next["confidence"] == "HIGH"
    assert res_next["manual_integration_required"] is False

    # 2. Vite + React
    vite_files = {
        "package.json": (
            '{"name": "my-vite-app", "dependencies": {"vite": "6.0.0", "react": "19.0.0"}}'
        ),
        "vite.config.ts": "export default {};",
    }
    res_vite = analyze_repository_manifests(vite_files)
    assert res_vite["detected_framework"] == DetectedFramework.VITE_REACT
    assert res_vite["confidence"] == "HIGH"

    # 3. Astro
    astro_files = {
        "package.json": '{"name": "my-astro-site", "dependencies": {"astro": "5.0.0"}}',
        "astro.config.mjs": "export default {};",
    }
    res_astro = analyze_repository_manifests(astro_files)
    assert res_astro["detected_framework"] == DetectedFramework.ASTRO

    # 4. Nuxt
    nuxt_files = {
        "package.json": '{"name": "my-nuxt-site", "dependencies": {"nuxt": "3.14.0"}}',
        "nuxt.config.ts": "export default defineNuxtConfig({});",
    }
    res_nuxt = analyze_repository_manifests(nuxt_files)
    assert res_nuxt["detected_framework"] == DetectedFramework.NUXT

    # 5. Remix
    remix_files = {
        "package.json": '{"name": "my-remix-app", "dependencies": {"@remix-run/react": "2.15.0"}}',
    }
    res_remix = analyze_repository_manifests(remix_files)
    assert res_remix["detected_framework"] == DetectedFramework.REMIX


def test_hostile_oversized_manifest_rejected():
    """Manifests exceeding 500 KB limit are rejected without processing (GH-3)."""
    oversized_content = " " * (500 * 1024 + 1)
    files = {"package.json": oversized_content}

    with pytest.raises(ValidationError) as exc:
        analyze_repository_manifests(files)
    assert "exceeds the maximum allowed limit" in str(exc.value)


@pytest.mark.parametrize(
    "traversal_path",
    [
        "../package.json",
        "../../etc/passwd",
        "sub/../../secret.json",
        "package.json\0evil",
        "/etc/package.json",
        "C:\\boot.ini",
    ],
)
def test_hostile_path_traversal_manifest_rejected(traversal_path):
    """Manifest file paths with path traversal or null bytes are rejected (GH-3)."""
    files = {traversal_path: '{"name": "traversal"}'}

    with pytest.raises(ValidationError) as exc:
        analyze_repository_manifests(files)
    assert "Hostile or invalid file path detected" in str(exc.value)


def test_hostile_malformed_json_rejected():
    """Syntax-corrupted or non-dict package.json is rejected safely without crashing."""
    corrupted_files = {"package.json": '{"name": "bad", dependencies: }'}
    with pytest.raises(ValidationError) as exc:
        analyze_repository_manifests(corrupted_files)
    assert "Invalid JSON syntax" in str(exc.value)

    list_json_files = {"package.json": '["not", "a", "dict"]'}
    with pytest.raises(ValidationError) as exc:
        analyze_repository_manifests(list_json_files)
    assert "must be a JSON object" in str(exc.value)


def test_zero_code_execution_invariant():
    """Ensure no subprocess, eval, or system command is executed during analysis (GH-3)."""
    with patch("subprocess.run") as mock_subproc, patch("subprocess.Popen") as mock_popen:
        files = {
            "package.json": (
                '{"name": "security-test", "scripts": {"postinstall": "rm -rf /"}, '
                '"dependencies": {"next": "15.0.0"}}'
            ),
            "next.config.js": "require('child_process').execSync('touch /tmp/pwned');",
        }
        res = analyze_repository_manifests(files)
        assert res["detected_framework"] == DetectedFramework.NEXT_JS
        mock_subproc.assert_not_called()
        mock_popen.assert_not_called()
