"""Safe static manifest analyzer detecting supported frontend frameworks (GH-3, GH-5)."""

from __future__ import annotations

import json
from typing import Any

from rest_framework.exceptions import ValidationError

from apps.github_integration.models import DetectedFramework
from apps.github_integration.validators import (
    validate_manifest_path,
    validate_manifest_size,
)

SUPPORTED_FRAMEWORK_DOCS: dict[str, str] = {
    DetectedFramework.NEXT_JS: "https://docs.cms.internal/integrations/nextjs",
    DetectedFramework.VITE_REACT: "https://docs.cms.internal/integrations/vite-react",
    DetectedFramework.ASTRO: "https://docs.cms.internal/integrations/astro",
    DetectedFramework.NUXT: "https://docs.cms.internal/integrations/nuxt",
    DetectedFramework.REMIX: "https://docs.cms.internal/integrations/remix",
    DetectedFramework.UNSUPPORTED: "https://docs.cms.internal/integrations/manual-integration",
}


def analyze_repository_manifests(files: dict[str, str]) -> dict[str, Any]:
    """Parse repository manifest files strictly as untrusted data to detect framework (GH-3, GH-5).

    Never executes customer code or shell scripts. Enforces bounded payload sizes.
    """
    for path, content in files.items():
        validate_manifest_path(path)
        validate_manifest_size(content)

    package_json_str = files.get("package.json")
    if not package_json_str:
        return {
            "detected_framework": DetectedFramework.UNSUPPORTED,
            "confidence": "NONE",
            "manual_integration_required": True,
            "integration_guide_url": SUPPORTED_FRAMEWORK_DOCS[DetectedFramework.UNSUPPORTED],
            "reason": "Missing package.json manifest in repository root.",
            "manifest_summary": {},
        }

    try:
        pkg_data = json.loads(package_json_str)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Invalid JSON syntax in package.json: {exc.msg}") from exc

    if not isinstance(pkg_data, dict):
        raise ValidationError("package.json must be a JSON object.")

    deps: dict[str, str] = {}
    if isinstance(pkg_data.get("dependencies"), dict):
        deps.update(pkg_data["dependencies"])
    if isinstance(pkg_data.get("devDependencies"), dict):
        deps.update(pkg_data["devDependencies"])

    # Detection logic based on official dependencies and config manifests
    has_next = "next" in deps or any(f.startswith("next.config.") for f in files)
    has_astro = "astro" in deps or any(f.startswith("astro.config.") for f in files)
    has_nuxt = "nuxt" in deps or any(f.startswith("nuxt.config.") for f in files)
    has_remix = (
        "@remix-run/react" in deps
        or "@remix-run/node" in deps
        or any(f.startswith("remix.config.") for f in files)
    )
    has_vite = "vite" in deps or any(f.startswith("vite.config.") for f in files)
    has_react = "react" in deps

    detected: str = DetectedFramework.UNSUPPORTED

    if has_next:
        detected = DetectedFramework.NEXT_JS
    elif has_astro:
        detected = DetectedFramework.ASTRO
    elif has_nuxt:
        detected = DetectedFramework.NUXT
    elif has_remix:
        detected = DetectedFramework.REMIX
    elif has_vite and has_react:
        detected = DetectedFramework.VITE_REACT

    if detected == DetectedFramework.UNSUPPORTED:
        return {
            "detected_framework": DetectedFramework.UNSUPPORTED,
            "confidence": "NONE",
            "manual_integration_required": True,
            "integration_guide_url": SUPPORTED_FRAMEWORK_DOCS[DetectedFramework.UNSUPPORTED],
            "reason": "No supported framework manifests identified.",
            "manifest_summary": {
                "package_name": pkg_data.get("name", ""),
                "dependencies_count": len(deps),
            },
        }

    return {
        "detected_framework": detected,
        "confidence": "HIGH",
        "manual_integration_required": False,
        "integration_guide_url": SUPPORTED_FRAMEWORK_DOCS[detected],
        "reason": f"Detected {detected} from package.json and configuration manifests.",
        "manifest_summary": {
            "package_name": pkg_data.get("name", ""),
            "framework": detected,
            "dependencies_count": len(deps),
        },
    }


def generate_integration_patch_files(
    framework: str,
    site_slug: str,
    public_api_url: str,
) -> dict[str, str]:
    """Generate safe, boilerplate integration client files for PR generation (GH-4)."""
    client_config = {
        "site_slug": site_slug,
        "api_endpoint": public_api_url,
        "version": "1.0",
        "generated_by": "CMS Backend GitHub Integration",
    }
    config_json = json.dumps(client_config, indent=2)

    files: dict[str, str] = {
        "cms.config.json": config_json,
    }

    if framework == DetectedFramework.NEXT_JS:
        files["lib/cms.ts"] = (
            "// CMS Client Loader for Next.js\n"
            "import config from '../cms.config.json';\n\n"
            "export async function getPublishedArticle(slug: string) {\n"
            "  const base = `${config.api_endpoint}/api/v1/public/sites/${config.site_slug}`;\n"
            "  const res = await fetch(`${base}/articles/${slug}/`);\n"
            "  if (!res.ok) return null;\n"
            "  return res.json();\n"
            "}\n"
        )
    elif framework == DetectedFramework.VITE_REACT:
        files["src/cmsClient.ts"] = (
            "// CMS Client Loader for Vite/React\n"
            "import config from '../cms.config.json';\n\n"
            "export async function fetchArticles() {\n"
            "  const base = `${config.api_endpoint}/api/v1/public/sites/${config.site_slug}`;\n"
            "  const res = await fetch(`${base}/articles/`);\n"
            "  return res.json();\n"
            "}\n"
        )
    elif framework == DetectedFramework.ASTRO:
        files["src/lib/cms.js"] = (
            "// CMS Client Loader for Astro\n"
            "import config from '../../cms.config.json';\n\n"
            "export async function getArticles() {\n"
            "  const base = `${config.api_endpoint}/api/v1/public/sites/${config.site_slug}`;\n"
            "  const res = await fetch(`${base}/articles/`);\n"
            "  return res.json();\n"
            "}\n"
        )
    else:
        files["cms-client.js"] = (
            f"// CMS Generic Client Loader\nconst config = {config_json};\nexport default config;\n"
        )

    return files
