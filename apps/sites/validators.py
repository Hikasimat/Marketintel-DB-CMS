"""Validators for domains and hostnames."""

import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

HOSTNAME_REGEX = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$"
)

RESERVED_HOSTNAMES = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",  # nosec B104  # noqa: S104
    "example.com",
    "example.org",
    "example.net",
    "test",
    "invalid",
}


def validate_hostname(value: str) -> str:
    """Validate RFC 1123 compliant hostname."""
    if not isinstance(value, str):
        raise ValidationError(_("Hostname must be a string."))

    normalized = value.strip().lower()

    if "/" in normalized or ":" in normalized or " " in normalized:
        raise ValidationError(_("Hostname cannot include protocols, ports, or paths."))

    if (
        normalized in RESERVED_HOSTNAMES
        or normalized.endswith(".local")
        or normalized.endswith(".internal")
    ):
        raise ValidationError(_("This hostname is reserved and cannot be registered."))

    if len(normalized) > 253:
        raise ValidationError(_("Hostname cannot exceed 253 characters."))

    if not HOSTNAME_REGEX.match(normalized):
        raise ValidationError(
            _("Invalid hostname format. Must be a valid FQDN (e.g. blog.example.com).")
        )

    return normalized
