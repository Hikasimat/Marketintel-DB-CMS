"""Shared fixtures for GitHub integration tests."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.github_integration.models import GitHubAppInstallation
from apps.sites.models import Site
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole

pytestmark = pytest.mark.django_db


@pytest.fixture
def github_setup():
    owner = User.objects.create_user(email="owner@github-test.com", password="Password123!")
    editor = User.objects.create_user(email="editor@github-test.com", password="Password123!")
    non_member = User.objects.create_user(
        email="nonmember@github-test.com", password="Password123!"
    )

    workspace = Workspace.objects.create(name="GitHub Integration WS", slug="github-ws")
    WorkspaceMembership.objects.create(workspace=workspace, user=owner, role=WorkspaceRole.OWNER)
    WorkspaceMembership.objects.create(workspace=workspace, user=editor, role=WorkspaceRole.EDITOR)

    site = Site.objects.create(workspace=workspace, name="GitHub Site", slug="github-site")

    installation = GitHubAppInstallation.objects.create(
        workspace=workspace,
        installation_id=12345,
        account_login="acme-corp",
        account_type="Organization",
        repository_selection="selected",
        permissions={"contents": "write", "pull_requests": "write"},
        is_active=True,
    )

    client = APIClient()

    return {
        "owner": owner,
        "editor": editor,
        "non_member": non_member,
        "workspace": workspace,
        "site": site,
        "installation": installation,
        "client": client,
    }
