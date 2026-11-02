"""Tests for Market Intel Google OAuth authentication enforcement & federation."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.tenancy.models import WorkspaceMembership, WorkspaceRole

pytestmark = pytest.mark.django_db


def test_login_with_valid_marketintel_token():
    client = APIClient()
    url = reverse("accounts:login")
    valid_token = "mock-valid-marketintel-token-analyst_user"

    response = client.post(url, {"token": valid_token}, format="json")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access" in data
    assert "refresh" in data

    # Verify user was provisioned
    user = User.objects.get(email="analyst_user@marketintel.internal")
    assert user.is_active is True

    # Verify user was enrolled into default workspace
    membership = WorkspaceMembership.objects.get(user=user)
    assert membership.workspace.slug == "default"
    assert membership.role == WorkspaceRole.EDITOR


def test_login_with_valid_marketintel_admin_token():
    client = APIClient()
    url = reverse("accounts:login")
    valid_admin_token = "mock-valid-marketintel-token-super_admin"

    response = client.post(url, {"token": valid_admin_token}, format="json")
    assert response.status_code == status.HTTP_200_OK

    user = User.objects.get(email="super_admin@marketintel.internal")
    assert user.is_staff is True

    membership = WorkspaceMembership.objects.get(user=user)
    assert membership.role == WorkspaceRole.OWNER


def test_login_with_invalid_marketintel_token_fails():
    client = APIClient()
    url = reverse("accounts:login")

    response = client.post(url, {"token": "invalid-garbage-token"}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_token_exchange_endpoint_success():
    client = APIClient()
    url = reverse("accounts:marketintel_exchange")
    valid_token = "mock-valid-marketintel-token-exchange_test"

    response = client.post(url, {"token": valid_token}, format="json")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access" in data
    assert "refresh" in data

    user = User.objects.get(email="exchange_test@marketintel.internal")
    assert user.is_active is True


def test_token_exchange_endpoint_invalid_token():
    client = APIClient()
    url = reverse("accounts:marketintel_exchange")

    response = client.post(url, {"token": "bad-token"}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_external_issuer_bearer_direct_access():
    client = APIClient()
    valid_token = "mock-valid-marketintel-token-direct_bearer"

    url = reverse("accounts:current_user")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {valid_token}")
    response = client.get(url)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["email"] == "direct_bearer@marketintel.internal"
