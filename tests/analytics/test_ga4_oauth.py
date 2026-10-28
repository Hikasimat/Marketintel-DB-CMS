"""Tests for GA4 authorized connection and encrypted credentials storage (ANA-2, SEC-3)."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.analytics.models import GA4Connection
from apps.analytics.validators import validate_ga4_property_id
from apps.sites.models import Site
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole


@pytest.fixture
def ga4_setup(db: None) -> dict[str, object]:
    admin = User.objects.create_user(email="admin@ga4.org", password="SecurePassword123!")
    analyst = User.objects.create_user(email="analyst@ga4.org", password="SecurePassword123!")

    workspace = Workspace.objects.create(name="GA4 Org", slug="ga4-org")
    WorkspaceMembership.objects.create(workspace=workspace, user=admin, role=WorkspaceRole.ADMIN)
    WorkspaceMembership.objects.create(
        workspace=workspace, user=analyst, role=WorkspaceRole.ANALYST
    )

    site = Site.objects.create(workspace=workspace, name="News", slug="news")

    return {
        "admin": admin,
        "analyst": analyst,
        "workspace": workspace,
        "site": site,
    }


def test_ga4_property_id_validation() -> None:
    assert validate_ga4_property_id("123456789") == "123456789"
    assert validate_ga4_property_id("properties/987654321") == "987654321"

    with pytest.raises(ValidationError, match="Invalid GA4 Property ID"):
        validate_ga4_property_id("not-a-number")

    with pytest.raises(ValidationError, match="Invalid GA4 Property ID"):
        validate_ga4_property_id("123")  # too short (< 6 digits)


@pytest.mark.django_db
def test_ga4_connection_encryption_at_rest(ga4_setup: dict[str, object]) -> None:
    site = ga4_setup["site"]
    assert isinstance(site, Site)

    raw_credentials = {
        "access_token": "ya29.a0AfH6SM-token-xyz-123456",
        "refresh_token": "1//04test_refresh_token",
        "client_id": "test-client-id.apps.googleusercontent.com",
        "client_secret": "super-secret-client-secret",  # nosec B105
    }

    conn = GA4Connection.objects.create(site=site, property_id="123456789")
    conn.set_credentials(raw_credentials)
    conn.save()

    # Verify database column is encrypted with AES-256-GCM envelope
    refreshed = GA4Connection.objects.get(id=conn.id)
    assert refreshed.encrypted_credentials.startswith("v1:")
    assert "super-secret-client-secret" not in refreshed.encrypted_credentials
    assert "ya29." not in refreshed.encrypted_credentials

    # Verify decryption
    decrypted = refreshed.get_credentials()
    assert decrypted["access_token"] == raw_credentials["access_token"]
    assert decrypted["refresh_token"] == raw_credentials["refresh_token"]

    assert "GA4 Connection (123456789)" in str(conn)


@pytest.mark.django_db
def test_ga4_connection_api_lifecycle(ga4_setup: dict[str, object]) -> None:
    client = APIClient()
    admin = ga4_setup["admin"]
    analyst = ga4_setup["analyst"]
    workspace = ga4_setup["workspace"]
    site = ga4_setup["site"]
    assert isinstance(workspace, Workspace)
    assert isinstance(site, Site)

    url = reverse(
        "analytics:ga4_connection",
        kwargs={"workspace_id": workspace.id, "site_id": site.id},
    )

    # 1. 404 when not configured
    client.force_authenticate(user=analyst)
    not_found_resp = client.get(url)
    assert not_found_resp.status_code == status.HTTP_404_NOT_FOUND

    # 2. Analyst cannot configure connection (requires admin)
    forbidden_resp = client.post(url, {"property_id": "123456789"})
    assert forbidden_resp.status_code == status.HTTP_403_FORBIDDEN

    # 3. Admin configures connection with write-only credentials
    client.force_authenticate(user=admin)
    create_resp = client.post(
        url,
        {
            "property_id": "123456789",
            "credentials": {
                "access_token": "secret-token",
                "refresh_token": "secret-refresh",
            },
        },
    )
    assert create_resp.status_code == status.HTTP_201_CREATED
    data = create_resp.json()
    assert data["property_id"] == "123456789"
    assert data["is_active"] is True
    # Verify credentials never leaked in API response
    assert "credentials" not in data or data.get("credentials") is None

    # 4. Analyst can now view status (without credentials)
    client.force_authenticate(user=analyst)
    view_resp = client.get(url)
    assert view_resp.status_code == status.HTTP_200_OK
    assert "credentials" not in view_resp.json() or view_resp.json().get("credentials") is None

    # 5. Admin disconnects connection
    client.force_authenticate(user=admin)
    del_resp = client.delete(url)
    assert del_resp.status_code == status.HTTP_204_NO_CONTENT
    assert not GA4Connection.objects.filter(site=site).exists()
