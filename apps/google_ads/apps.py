"""Google Ads Django app configuration."""

from django.apps import AppConfig


class GoogleAdsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.google_ads"
    verbose_name = "Google Ads Integration"

