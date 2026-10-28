"""Validators for canonical URLs, redirects, and safe JSON-LD structured data.

Requirements satisfied: SEO-2, SEO-3, SEO-4.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from apps.sites.models import Site

ALLOWLISTED_JSONLD_TYPES = {
    "Article",
    "BlogPosting",
    "NewsArticle",
    "WebPage",
    "Organization",
    "BreadcrumbList",
    "WebSite",
    "Person",
}


def normalize_path(path: str) -> str:
    """Normalize URL path with leading slash, without redundant or trailing slashes."""
    p = path.strip()
    if not p.startswith("/"):
        p = "/" + p
    # Collapse multiple consecutive slashes
    p = re.sub(r"/+", "/", p)
    if len(p) > 1 and p.endswith("/"):
        p = p[:-1]
    return p


def validate_canonical_url(canonical_url: str, site: Site) -> str:
    """Validate canonical URL against site registered domains or relative paths (SEO-2)."""
    val = canonical_url.strip()
    if not val:
        return ""

    if val.startswith("/"):
        return normalize_path(val)

    parsed = urllib.parse.urlparse(val)
    if parsed.scheme not in ("http", "https"):
        raise ValidationError(
            _("Canonical URL must have an http or https scheme or be a relative path.")
        )

    if not parsed.netloc:
        raise ValidationError(_("Canonical URL must include a valid host."))

    host = parsed.netloc.lower().split(":")[0]

    # Verify hostname belongs to site domains or allowed origins
    site_domains = set(site.domains.values_list("hostname", flat=True))
    allowed_hosts = {h.lower() for h in site_domains}

    # Also extract hosts from allowed_origins
    for origin in site.allowed_origins:
        if origin == "*":
            continue
        try:
            o_parsed = urllib.parse.urlparse(origin)
            if o_parsed.netloc:
                allowed_hosts.add(o_parsed.netloc.lower().split(":")[0])
        except (ValueError, AttributeError):
            pass

    if allowed_hosts and host not in allowed_hosts:
        raise ValidationError(
            _(
                f"Canonical URL host '{host}' does not match any registered "
                "or allowed domain for this site."
            )
        )

    return val


def validate_redirect_rule(
    site: Site,
    source_path: str,
    target_url: str,
    rule_id: Any = None,
) -> tuple[str, str]:
    """Validate redirect source, target, open-redirect defense, and cycles (SEO-4)."""
    src = normalize_path(source_path)
    target = target_url.strip()

    if not target:
        raise ValidationError({"target_url": [_("Target URL is required.")]})

    # Prevent direct self-redirect
    if target.startswith("/"):
        target_normalized = normalize_path(target)
        if src == target_normalized:
            raise ValidationError(
                {"target_url": [_("A URL cannot redirect to itself (immediate loop).")]}
            )
    else:
        # Absolute URL: validate scheme and prevent open redirects
        parsed = urllib.parse.urlparse(target)
        if parsed.scheme not in ("http", "https"):
            raise ValidationError(
                {"target_url": [_("Target URL must be a relative path or an http/https URL.")]}
            )

        target_host = parsed.netloc.lower().split(":")[0]
        site_hosts = set(site.domains.values_list("hostname", flat=True))
        for origin in site.allowed_origins:
            if origin == "*":
                site_hosts.add(target_host)  # Wildcard allows any destination
                break
            try:
                o_parsed = urllib.parse.urlparse(origin)
                if o_parsed.netloc:
                    site_hosts.add(o_parsed.netloc.lower().split(":")[0])
            except (ValueError, AttributeError):
                pass

        if site_hosts and target_host not in site_hosts:
            raise ValidationError(
                {
                    "target_url": [
                        _(
                            f"Open redirect prohibited. Target host '{target_host}' "
                            "is not an authorized destination."
                        )
                    ]
                }
            )

    # Loop and chain depth detection across existing active redirect rules
    from apps.seo.models import RedirectRule

    active_rules_qs = RedirectRule.objects.filter(site=site, is_active=True)
    if rule_id:
        active_rules_qs = active_rules_qs.exclude(id=rule_id)

    # Build routing graph
    routes: dict[str, str] = {rule.source_path: rule.target_url for rule in active_rules_qs}
    routes[src] = target

    # Check all chains in routes for loops and max depth
    for start_node in list(routes.keys()):
        visited = [start_node]
        curr = routes[start_node]
        for _step in range(15):
            if not curr.startswith("/"):
                # External hop terminates internal chain
                break
            curr_norm = normalize_path(curr)
            if curr_norm in visited:
                loop_path = " -> ".join([*visited, curr_norm])
                raise ValidationError({"target_url": [f"Redirect loop detected: {loop_path}."]})
            visited.append(curr_norm)
            if curr_norm in routes:
                curr = routes[curr_norm]
            else:
                break

        if len(visited) > 5:
            raise ValidationError(
                {
                    "target_url": [
                        f"Redirect chain too long ({len(visited)} hops). Maximum allowed is 5 hops."
                    ]
                }
            )

    return src, target


def validate_jsonld_schema(data: dict[str, Any]) -> dict[str, Any]:
    """Validate JSON-LD structured data allowlisted types and structure (SEO-3)."""
    if not isinstance(data, dict):
        raise ValidationError(_("JSON-LD payload must be a JSON object."))

    if not data:
        return {}

    context = data.get("@context", "")
    if "schema.org" not in str(context):
        raise ValidationError(_("JSON-LD '@context' must reference schema.org."))

    schema_type = data.get("@type")
    if not schema_type or schema_type not in ALLOWLISTED_JSONLD_TYPES:
        allowed = ", ".join(sorted(ALLOWLISTED_JSONLD_TYPES))
        raise ValidationError(
            _(f"Unsupported or missing JSON-LD '@type'. Allowed types: {allowed}.")
        )

    return data


def escape_jsonld_for_html(data: dict[str, Any]) -> str:
    """Safely serialize JSON-LD preventing </script> injection and line separator issues (SEO-3)."""
    json_str = json.dumps(data, ensure_ascii=False)
    # Prevent closing </script> tag inside script element
    safe_str = json_str.replace("</", "<\\/")
    # Escape Unicode line terminators U+2028 and U+2029
    safe_str = safe_str.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return safe_str
