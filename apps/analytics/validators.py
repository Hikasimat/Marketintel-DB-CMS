"""Validators and sanitizers for analytics configuration and event ingestion."""

from __future__ import annotations

import re
from typing import Any

from rest_framework.exceptions import ValidationError

# GA4 Measurement ID: G-XXXXXXXXXX (alphanumeric uppercase)
GA4_MEASUREMENT_ID_REGEX = re.compile(r"^G-[A-Z0-9]+$")

# GTM Container ID: GTM-XXXXXXXX (alphanumeric uppercase)
GTM_CONTAINER_ID_REGEX = re.compile(r"^GTM-[A-Z0-9]+$")

# GA4 Property ID: digits only, e.g. 123456789 or properties/123456789
GA4_PROPERTY_ID_REGEX = re.compile(r"^(properties/)?(\d{6,16})$")

# PII regex patterns: emails, phone numbers, SSN patterns
EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_PATTERN = re.compile(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

# HTML/Script injection detection
HTML_TAG_PATTERN = re.compile(r"<[^>]+>|javascript:|data:text/html", re.IGNORECASE)

# Query param PII indicators
PII_QUERY_PARAMS = {
    "email",
    "user_email",
    "password",
    "token",
    "ssn",
    "phone",
    "first_name",
    "last_name",
    "name",
}

# Allowlisted properties per event type (ANA-4)
ALLOWLISTED_EVENT_PROPERTIES: dict[str, set[str]] = {
    "page_view": {"path", "referrer", "title"},
    "cta_click": {"path", "cta_id", "cta_text", "target_url"},
    "form_submit": {"path", "form_id", "form_name"},
}


def validate_measurement_id(value: str) -> str:
    """Validate GA4 measurement ID format (e.g. G-ABC123XYZ)."""
    if not value:
        return ""
    val = value.strip().upper()
    if not GA4_MEASUREMENT_ID_REGEX.match(val):
        raise ValidationError("Invalid GA4 Measurement ID format. Expected format 'G-XXXXXXXX'.")
    return val


def validate_gtm_container_id(value: str) -> str:
    """Validate GTM container ID format (e.g. GTM-XXXXXX)."""
    if not value:
        return ""
    val = value.strip().upper()
    if not GTM_CONTAINER_ID_REGEX.match(val):
        raise ValidationError("Invalid GTM Container ID format. Expected format 'GTM-XXXXXXXX'.")
    return val


def validate_ga4_property_id(value: str) -> str:
    """Validate and normalize numeric GA4 Property ID."""
    if not value:
        return ""
    match = GA4_PROPERTY_ID_REGEX.match(value.strip())
    if not match:
        raise ValidationError("Invalid GA4 Property ID. Expected a numeric property ID.")
    return match.group(2)


def sanitize_url_query(url_or_path: str) -> str:
    """Strip known PII query parameters from URLs and paths."""
    from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

    parsed = urlparse(url_or_path)
    if not parsed.query:
        return url_or_path

    filtered_pairs = []
    for k, v in parse_qsl(parsed.query, keep_blank_values=True):
        if k.lower() not in PII_QUERY_PARAMS:
            filtered_pairs.append((k, v))

    new_query = urlencode(filtered_pairs)
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )


def detect_pii(text: str) -> bool:
    """Check if a string contains common PII patterns."""
    if EMAIL_PATTERN.search(text) or PHONE_PATTERN.search(text):
        return True
    return bool(SSN_PATTERN.search(text))


def validate_event_properties(event_type: str, properties: dict[str, Any]) -> dict[str, Any]:
    """Validate that properties are allowlisted, free of PII, and free of HTML/script injection."""
    allowed = ALLOWLISTED_EVENT_PROPERTIES.get(event_type)
    if allowed is None:
        raise ValidationError(
            f"Unsupported event type '{event_type}'. "
            f"Allowed types: {sorted(ALLOWLISTED_EVENT_PROPERTIES.keys())}"
        )

    # Rejection of arbitrary non-allowlisted keys (ANA-4)
    extra_keys = set(properties.keys()) - allowed
    if extra_keys:
        raise ValidationError(
            f"Non-allowlisted property keys for '{event_type}': {sorted(extra_keys)}. "
            f"Allowed keys: {sorted(allowed)}"
        )

    cleaned_properties: dict[str, Any] = {}
    for key, value in properties.items():
        if value is None:
            continue

        if not isinstance(value, str):
            value = str(value)

        # Enforce string length bound
        if len(value) > 500:
            raise ValidationError(f"Property '{key}' exceeds maximum length of 500 characters.")

        # Rejection of HTML tags and script injections
        if HTML_TAG_PATTERN.search(value):
            raise ValidationError(
                f"Property '{key}' contains prohibited HTML or script characters."
            )

        # Rejection of PII patterns
        if detect_pii(value):
            raise ValidationError(f"Property '{key}' contains prohibited personal data (PII).")

        # Sanitize URLs if it's a path or referrer
        if key in ("path", "referrer", "target_url"):
            value = sanitize_url_query(value)

        cleaned_properties[key] = value

    return cleaned_properties


def coarsen_user_agent(ua_string: str) -> tuple[str, str]:
    """Coarsen raw User-Agent to device category and browser family (ANA-5).

    Never stores raw UA string or fingerprinting details.
    """
    if not ua_string:
        return "UNKNOWN", "OTHER"

    ua = ua_string.lower()

    # Detect bots
    if any(bot in ua for bot in ("bot", "spider", "crawler", "archiver", "curl", "wget")):
        return "BOT", "OTHER"

    # Device category
    if "tablet" in ua or "ipad" in ua:
        device = "TABLET"
    elif "mobile" in ua or "android" in ua or "iphone" in ua:
        device = "MOBILE"
    else:
        device = "DESKTOP"

    # Browser family
    if "edg" in ua:
        browser = "EDGE"
    elif "chrome" in ua or "crios" in ua:
        browser = "CHROME"
    elif "safari" in ua and "chrome" not in ua:
        browser = "SAFARI"
    elif "firefox" in ua or "fxios" in ua:
        browser = "FIREFOX"
    else:
        browser = "OTHER"

    return device, browser
