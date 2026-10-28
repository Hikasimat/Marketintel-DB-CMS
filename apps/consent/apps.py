"""Consent application configuration."""

from django.apps import AppConfig


class ConsentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.consent"
    verbose_name = "Consent and Cookie Preferences"
