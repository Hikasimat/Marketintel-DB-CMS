"""GitHub integration application configuration."""

from django.apps import AppConfig


class GitHubIntegrationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.github_integration"
    verbose_name = "GitHub Repository Integration"
