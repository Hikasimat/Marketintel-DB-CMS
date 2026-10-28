"""Tests for integrations models, credential envelope encryption at rest, and key generation."""

from __future__ import annotations

import pytest

from apps.accounts.models import User
from apps.integrations.models import (
    IndexNowKey,
    IndexSubmissionLog,
    SearchEngineConnection,
    SearchProvider,
    SubmissionStatus,
)
from apps.sites.models import Domain, Site
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole


@pytest.fixture
def site_setup(db: None) -> dict[str, object]:
    user = User.objects.create_user(email="owner@test.com", password="SecurePassword123!")
    workspace = Workspace.objects.create(name="Test Org", slug="test-org")
    WorkspaceMembership.objects.create(workspace=workspace, user=user, role=WorkspaceRole.OWNER)
    site = Site.objects.create(workspace=workspace, name="Site One", slug="site-one")
    Domain.objects.create(
        site=site, hostname="primary.example.com", is_verified=True, is_primary=True
    )
    return {"user": user, "workspace": workspace, "site": site}


@pytest.mark.django_db
def test_search_connection_encryption_at_rest(site_setup: dict[str, object]) -> None:
    site = site_setup["site"]
    assert isinstance(site, Site)

    raw_api_key = "super-secret-google-oauth-token-123456789"  # nosec B105
    conn = SearchEngineConnection.objects.create(
        site=site,
        provider=SearchProvider.GOOGLE,
    )
    conn.set_credentials(raw_api_key)
    conn.save()

    # Verify at-rest representation in database is encrypted
    refreshed = SearchEngineConnection.objects.get(id=conn.id)
    assert refreshed.encrypted_credentials != raw_api_key
    assert refreshed.encrypted_credentials.startswith("v1:")
    assert raw_api_key not in refreshed.encrypted_credentials

    # Verify decryption
    assert refreshed.get_credentials() == raw_api_key

    # Test empty credentials
    refreshed.set_credentials("")
    assert refreshed.encrypted_credentials == ""
    assert refreshed.get_credentials() == ""

    # Test str representation
    assert "Google Search Console" in str(conn)


@pytest.mark.django_db
def test_indexnow_key_generation(site_setup: dict[str, object]) -> None:
    site = site_setup["site"]
    assert isinstance(site, Site)

    key_obj = IndexNowKey.generate_for_site(site)
    assert len(key_obj.key) == 32
    assert key_obj.key_location == f"https://primary.example.com/{key_obj.key}.txt"
    assert "IndexNow Key for" in str(key_obj)

    # Calling generate_for_site again rotates and updates existing record
    new_key_obj = IndexNowKey.generate_for_site(site)
    assert new_key_obj.id == key_obj.id
    assert new_key_obj.key != key_obj.key


@pytest.mark.django_db
def test_index_submission_log_lifecycle(site_setup: dict[str, object]) -> None:
    site = site_setup["site"]
    assert isinstance(site, Site)

    log = IndexSubmissionLog.objects.create(
        site=site,
        provider=SearchProvider.BING,
        urls=["https://primary.example.com/post-1"],
        idempotency_key="idemp-key-123",
        status=SubmissionStatus.PENDING,
    )

    assert log.status == SubmissionStatus.PENDING
    assert log.retry_count == 0
    assert "BING submission for site-one" in str(log)
