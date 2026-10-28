"""Serializers for GitHub App installations, repository connections, and PR generation."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.github_integration.models import (
    DetectedFramework,
    GitHubAppInstallation,
    SiteGitHubRepoConnection,
)
from apps.github_integration.validators import (
    validate_branch_name,
    validate_repo_full_name,
)


class GitHubAppInstallationSerializer(serializers.ModelSerializer[GitHubAppInstallation]):
    """Serializer for active GitHub App installations (GH-1)."""

    workspace_id = serializers.UUIDField(source="workspace.id", read_only=True)

    class Meta:
        model = GitHubAppInstallation
        fields = (
            "id",
            "workspace_id",
            "installation_id",
            "account_login",
            "account_type",
            "repository_selection",
            "permissions",
            "is_active",
            "suspended_at",
            "installed_at",
            "updated_at",
        )
        read_only_fields = ("id", "workspace_id", "installed_at", "updated_at")


class GitHubAppInstallationRegisterSerializer(serializers.Serializer[Any]):
    """Payload serializer for registering a newly authorized installation."""

    installation_id = serializers.IntegerField(min_value=1)
    account_login = serializers.CharField(max_length=255)
    account_type = serializers.CharField(max_length=50, default="User")
    repository_selection = serializers.CharField(max_length=20, default="selected")
    permissions = serializers.DictField(required=False, default=dict)


class SiteGitHubRepoConnectionSerializer(serializers.ModelSerializer[SiteGitHubRepoConnection]):
    """Serializer for repository-to-site connection details (GH-2, GH-4)."""

    site_id = serializers.UUIDField(source="site.id", read_only=True)
    installation_id = serializers.IntegerField(
        source="installation.installation_id", read_only=True
    )

    class Meta:
        model = SiteGitHubRepoConnection
        fields = (
            "id",
            "site_id",
            "installation_id",
            "repo_full_name",
            "default_branch",
            "selected_branch",
            "detected_framework",
            "framework_manifest",
            "integration_status",
            "last_pr_url",
            "last_pr_number",
            "last_synced_at",
            "last_error",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class GitHubRepoConnectSerializer(serializers.Serializer[Any]):
    """Payload serializer for connecting an authorized repository to a site (GH-2)."""

    installation_id = serializers.IntegerField(
        help_text="Numeric installation ID of the authorized GitHub App."
    )
    repo_full_name = serializers.CharField(max_length=255)
    selected_branch = serializers.CharField(max_length=100, default="main")

    def validate_repo_full_name(self, value: str) -> str:
        validate_repo_full_name(value)
        return value

    def validate_selected_branch(self, value: str) -> str:
        validate_branch_name(value)
        return value


class FrameworkDetectionResponseSerializer(serializers.Serializer[Any]):
    """Result serializer for framework analysis from untrusted manifests (GH-3, GH-5)."""

    detected_framework = serializers.ChoiceField(choices=DetectedFramework.choices)
    confidence = serializers.CharField()
    manual_integration_required = serializers.BooleanField()
    integration_guide_url = serializers.URLField()
    reason = serializers.CharField()
    manifest_summary = serializers.DictField()


class IntegrationPROpenSerializer(serializers.Serializer[Any]):
    """Payload serializer for opening an integration pull request (GH-4)."""

    commit_message = serializers.CharField(
        max_length=255, default="Add CMS integration client configuration"
    )
    pr_title = serializers.CharField(max_length=255, default="CMS Integration Setup")
    pr_body = serializers.CharField(
        required=False,
        default=(
            "### CMS Backend Integration\n\n"
            "This Pull Request adds the required configuration and client helper files "
            "to connect your frontend to the headless CMS API."
        ),
    )
    branch_name = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default=""
    )

    def validate_branch_name(self, value: str) -> str:
        if value:
            validate_branch_name(value)
        return value


class IntegrationPRResponseSerializer(serializers.Serializer[Any]):
    """Response serializer after pull request creation (GH-4)."""

    pr_number = serializers.IntegerField()
    pr_url = serializers.URLField()
    base_branch = serializers.CharField()
    new_branch = serializers.CharField()
    title = serializers.CharField()
    committed_files = serializers.ListField(child=serializers.CharField())
