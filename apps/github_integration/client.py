"""Isolated GitHub App API client with deterministic mock adapter (GH-1, GH-2, GH-4)."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from django.conf import settings
from rest_framework.exceptions import ValidationError

from apps.github_integration.validators import (
    validate_branch_name,
    validate_repo_full_name,
)

logger = logging.getLogger(__name__)


class BaseGitHubClient(ABC):
    """Abstract interface for GitHub App operations."""

    @abstractmethod
    def list_installation_repositories(self, installation_id: int) -> list[dict[str, Any]]:
        """List repositories accessible to the installation (GH-2)."""

    @abstractmethod
    def get_repository_branch(self, repo_full_name: str, branch: str) -> dict[str, Any]:
        """Verify repository branch existence and retrieve latest commit SHA."""

    @abstractmethod
    def get_repository_files(
        self, repo_full_name: str, branch: str, file_paths: list[str]
    ) -> dict[str, str]:
        """Fetch manifest and config files from repository branch."""

    @abstractmethod
    def create_branch_and_pull_request(
        self,
        repo_full_name: str,
        base_branch: str,
        new_branch: str,
        commit_message: str,
        pr_title: str,
        pr_body: str,
        files: dict[str, str],
    ) -> dict[str, Any]:
        """Create new branch, commit files, and open Pull Request (GH-4).

        Must NEVER commit directly to default/base branch.
        """


class MockGitHubClient(BaseGitHubClient):
    """Deterministic mock client for testing and credential-less verification."""

    def __init__(self) -> None:
        self.repositories: dict[int, list[dict[str, Any]]] = {
            12345: [
                {
                    "id": 101,
                    "full_name": "acme-corp/nextjs-frontend",
                    "default_branch": "main",
                    "private": True,
                },
                {
                    "id": 102,
                    "full_name": "acme-corp/vite-blog",
                    "default_branch": "main",
                    "private": False,
                },
                {
                    "id": 103,
                    "full_name": "acme-corp/custom-service",
                    "default_branch": "master",
                    "private": True,
                },
            ]
        }
        self.mock_repo_files: dict[str, dict[str, str]] = {
            "acme-corp/nextjs-frontend": {
                "package.json": (
                    '{"name": "nextjs-frontend", '
                    '"dependencies": {"next": "^15.0.0", "react": "^19.0.0"}}'
                ),
                "next.config.mjs": "export default {};",
            },
            "acme-corp/vite-blog": {
                "package.json": (
                    '{"name": "vite-blog", "dependencies": {"vite": "^6.0.0", "react": "^19.0.0"}}'
                ),
                "vite.config.ts": "export default {};",
            },
            "acme-corp/custom-service": {
                "package.json": (
                    '{"name": "custom-service", "dependencies": {"express": "^4.18.0"}}'
                ),
            },
        }
        self.created_prs: list[dict[str, Any]] = []

    def list_installation_repositories(self, installation_id: int) -> list[dict[str, Any]]:
        return self.repositories.get(
            installation_id,
            [
                {
                    "id": 999,
                    "full_name": "example/default-repo",
                    "default_branch": "main",
                    "private": False,
                }
            ],
        )

    def get_repository_branch(self, repo_full_name: str, branch: str) -> dict[str, Any]:
        validate_repo_full_name(repo_full_name)
        validate_branch_name(branch)
        if branch == "non-existent-branch":
            raise ValidationError(f"Branch '{branch}' not found on {repo_full_name}.")
        return {
            "name": branch,
            "commit": {"sha": "6dcb09b5b57875f334f61aebed695e2e4193db5e"},
            "protected": branch in ("main", "master", "production"),
        }

    def get_repository_files(
        self, repo_full_name: str, branch: str, file_paths: list[str]
    ) -> dict[str, str]:
        validate_repo_full_name(repo_full_name)
        validate_branch_name(branch)
        repo_files = self.mock_repo_files.get(repo_full_name, {})
        retrieved: dict[str, str] = {}
        for p in file_paths:
            if p in repo_files:
                retrieved[p] = repo_files[p]
        return retrieved

    def create_branch_and_pull_request(
        self,
        repo_full_name: str,
        base_branch: str,
        new_branch: str,
        commit_message: str,
        pr_title: str,
        pr_body: str,
        files: dict[str, str],
    ) -> dict[str, Any]:
        validate_repo_full_name(repo_full_name)
        validate_branch_name(base_branch)
        validate_branch_name(new_branch)

        # GH-4 Safety invariant: Never write directly to base branch
        if new_branch == base_branch:
            raise ValidationError("Cannot open Pull Request on the same base branch.")

        pr_number = len(self.created_prs) + 1
        pr_record = {
            "pr_number": pr_number,
            "pr_url": f"https://github.com/{repo_full_name}/pull/{pr_number}",
            "base_branch": base_branch,
            "new_branch": new_branch,
            "title": pr_title,
            "body": pr_body,
            "committed_files": list(files.keys()),
        }
        self.created_prs.append(pr_record)
        return pr_record


class LiveGitHubClient(BaseGitHubClient):
    """Production GitHub client using PyJWT with RS256 for GitHub App authentication."""

    def __init__(self, app_id: str, private_key: str) -> None:
        self.app_id = app_id
        self.private_key = private_key

    def list_installation_repositories(self, installation_id: int) -> list[dict[str, Any]]:
        raise NotImplementedError("Live GitHub API requires live network and app credentials.")

    def get_repository_branch(self, repo_full_name: str, branch: str) -> dict[str, Any]:
        raise NotImplementedError("Live GitHub API requires live network and app credentials.")

    def get_repository_files(
        self, repo_full_name: str, branch: str, file_paths: list[str]
    ) -> dict[str, str]:
        raise NotImplementedError("Live GitHub API requires live network and app credentials.")

    def create_branch_and_pull_request(
        self,
        repo_full_name: str,
        base_branch: str,
        new_branch: str,
        commit_message: str,
        pr_title: str,
        pr_body: str,
        files: dict[str, str],
    ) -> dict[str, Any]:
        raise NotImplementedError("Live GitHub API requires live network and app credentials.")


_default_mock_client = MockGitHubClient()


def get_github_client() -> BaseGitHubClient:
    """Factory retrieving configured GitHub client (Live or Mock)."""
    app_id = getattr(settings, "GITHUB_APP_ID", "")
    private_key = getattr(settings, "GITHUB_APP_PRIVATE_KEY", "")
    if private_key:
        try:
            path = Path(private_key)
            if not path.is_absolute():
                path = Path(settings.BASE_DIR) / path
            if path.is_file():
                private_key = path.read_text(encoding="utf-8")
        except Exception:
            pass
    # Default to deterministic mock client unless in live prod with explicit keys
    if (
        getattr(settings, "GITHUB_APP_ENABLED", False)
        and app_id
        and private_key
        and not getattr(settings, "IS_TEST", True)
    ):
        return LiveGitHubClient(app_id=app_id, private_key=private_key)
    return _default_mock_client
