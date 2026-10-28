"""Password policy and complexity validators."""

import re
from typing import Any

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class PasswordComplexityValidator:
    """Enforce minimum 12 chars, uppercase, lowercase, digit, and symbol."""

    def __init__(self, min_length: int = 12) -> None:
        self.min_length = min_length

    def validate(self, password: str, user: Any = None) -> None:
        if len(password) < self.min_length:
            raise ValidationError(
                _("Password must be at least %(min_length)d characters long."),
                code="password_too_short",
                params={"min_length": self.min_length},
            )
        if not re.search(r"[A-Z]", password):
            raise ValidationError(
                _("Password must contain at least one uppercase letter."),
                code="password_no_upper",
            )
        if not re.search(r"[a-z]", password):
            raise ValidationError(
                _("Password must contain at least one lowercase letter."),
                code="password_no_lower",
            )
        if not re.search(r"\d", password):
            raise ValidationError(
                _("Password must contain at least one numerical digit."),
                code="password_no_digit",
            )
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            raise ValidationError(
                _("Password must contain at least one special symbol."),
                code="password_no_symbol",
            )

    def get_help_text(self) -> str:
        return _(
            "Your password must contain at least 12 characters, including uppercase, "
            "lowercase, numbers, and special symbols."
        )
