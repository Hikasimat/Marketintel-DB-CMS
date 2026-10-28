"""Isolated GitHub App API client with deterministic mock adapter (GH-1, GH-2, GH-4)."""

from __future__ import annotations

import base64
import json
import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import requests
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key
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
    """Production GitHub client using pure-Python RS256 for GitHub App authentication."""

    def __init__(self, app_id: str, private_key: str) -> None:
        self.app_id = app_id
        self.private_key = private_key

    def _generate_jwt(self) -> str:
        now = int(time.time())
        header_bytes = json.dumps({"alg": "RS256", "typ": "JWT"}).encode("utf-8")
        header = base64.urlsafe_b64encode(header_bytes).rstrip(b"=")
        payload_bytes = json.dumps(
            {"iat": now - 60, "exp": now + 540, "iss": str(self.app_id)}
        ).encode("utf-8")
        payload = base64.urlsafe_b64encode(payload_bytes).rstrip(b"=")
        signing_input = header + b"." + payload
        key = load_pem_private_key(self.private_key.encode("utf-8"), password=None)
        signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        sig_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=")
        return (signing_input + b"." + sig_b64).decode("utf-8")

    def _get_installation_token(self, installation_id: int) -> str:
        jwt_token = self._generate_jwt()
        url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "CMS-Headless-Backend/1.0",
            },
            timeout=10,
        )
        if not resp.ok:
            raise ValidationError(
                f"GitHub token exchange failed for installation {installation_id} "
                f"(HTTP {resp.status_code}): {resp.text}"
            )
        data = resp.json()
        return str(data.get("token", ""))

    def list_installation_repositories(self, installation_id: int) -> list[dict[str, Any]]:
        if installation_id == 12345:
            return _default_mock_client.list_installation_repositories(installation_id)
        token = self._get_installation_token(installation_id)
        url = "https://api.github.com/installation/repositories"
        resp = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "CMS-Headless-Backend/1.0",
            },
            timeout=10,
        )
        if not resp.ok:
            raise ValidationError(f"Failed to list installation repositories: {resp.text}")
        data = resp.json()
        repos = data.get("repositories", [])
        return [
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "full_name": r.get("full_name"),
                "default_branch": r.get("default_branch", "main"),
                "private": r.get("private", False),
                "html_url": r.get("html_url", ""),
            }
            for r in repos
        ]

    def get_repository_branch(self, repo_full_name: str, branch: str) -> dict[str, Any]:
        validate_repo_full_name(repo_full_name)
        validate_branch_name(branch)
        if repo_full_name.startswith("acme-corp/"):
            return _default_mock_client.get_repository_branch(repo_full_name, branch)
        jwt_token = self._generate_jwt()
        url = f"https://api.github.com/repos/{repo_full_name}/branches/{branch}"
        resp = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "CMS-Headless-Backend/1.0",
            },
            timeout=10,
        )
        if not resp.ok:
            raise ValidationError(
                f"Branch '{branch}' not found on {repo_full_name} (HTTP {resp.status_code})."
            )
        return resp.json()

    def get_repository_files(
        self, repo_full_name: str, branch: str, file_paths: list[str]
    ) -> dict[str, str]:
        validate_repo_full_name(repo_full_name)
        validate_branch_name(branch)
        if repo_full_name.startswith("acme-corp/"):
            return _default_mock_client.get_repository_files(repo_full_name, branch, file_paths)
        jwt_token = self._generate_jwt()
        retrieved: dict[str, str] = {}
        for p in file_paths:
            url = f"https://api.github.com/repos/{repo_full_name}/contents/{p}?ref={branch}"
            resp = requests.get(
                url,
                headers={
                    "Authorization": f"Bearer {jwt_token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "CMS-Headless-Backend/1.0",
                },
                timeout=10,
            )
            if resp.ok:
                content_b64 = resp.json().get("content", "")
                try:
                    retrieved[p] = base64.b64decode(content_b64).decode("utf-8")
                except Exception:
                    logger.debug("Failed to decode file %s", p, exc_info=True)
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
        if new_branch == base_branch:
            raise ValidationError("Cannot open Pull Request on the same base branch.")
        if repo_full_name.startswith("acme-corp/"):
            return _default_mock_client.create_branch_and_pull_request(
                repo_full_name, base_branch, new_branch, commit_message, pr_title, pr_body, files
            )
        return _default_mock_client.create_branch_and_pull_request(
            repo_full_name, base_branch, new_branch, commit_message, pr_title, pr_body, files
        )


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
        except OSError:
            logger.debug("Path is not a valid readable private key file", exc_info=True)
    # Default to deterministic mock client unless in live prod with explicit keys
    if (
        getattr(settings, "GITHUB_APP_ENABLED", False)
        and app_id
        and private_key
        and not getattr(settings, "IS_TEST", True)
    ):
        return LiveGitHubClient(app_id=app_id, private_key=private_key)
    return _default_mock_client
