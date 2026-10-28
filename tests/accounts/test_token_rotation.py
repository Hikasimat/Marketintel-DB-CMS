"""Tests for JWT token rotation and family-reuse detection."""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import RefreshTokenFamily, User

pytestmark = pytest.mark.django_db


def test_token_rotation_success():
    client = APIClient()
    user = User.objects.create_user(email="rotate@example.com", password="SecurePassword123!")

    # Login to get initial tokens
    login_url = reverse("accounts:login")
    login_resp = client.post(
        login_url, {"email": user.email, "password": "SecurePassword123!"}, format="json"
    )
    assert login_resp.status_code == status.HTTP_200_OK
    initial_refresh = login_resp.json()["refresh"]

    # Rotate token
    refresh_url = reverse("accounts:refresh")
    refresh_resp = client.post(refresh_url, {"refresh": initial_refresh}, format="json")
    assert refresh_resp.status_code == status.HTTP_200_OK

    data = refresh_resp.json()
    assert "access" in data
    assert "refresh" in data
    rotated_refresh = data["refresh"]
    assert rotated_refresh != initial_refresh

    # Using the rotated refresh token succeeds again
    refresh_resp_2 = client.post(refresh_url, {"refresh": rotated_refresh}, format="json")
    assert refresh_resp_2.status_code == status.HTTP_200_OK


def test_token_family_reuse_detection_revokes_lineage():
    client = APIClient()
    user = User.objects.create_user(email="reuse@example.com", password="SecurePassword123!")

    # Login
    login_resp = client.post(
        reverse("accounts:login"),
        {"email": user.email, "password": "SecurePassword123!"},
        format="json",
    )
    token_1 = login_resp.json()["refresh"]

    # First rotation: token_1 -> token_2
    refresh_url = reverse("accounts:refresh")
    refresh_resp_1 = client.post(refresh_url, {"refresh": token_1}, format="json")
    assert refresh_resp_1.status_code == status.HTTP_200_OK
    token_2 = refresh_resp_1.json()["refresh"]

    # ATTACK / REUSE: An attacker tries to reuse token_1!
    reuse_resp = client.post(refresh_url, {"refresh": token_1}, format="json")
    assert reuse_resp.status_code == status.HTTP_401_UNAUTHORIZED
    data = reuse_resp.json()
    assert data["error"]["code"] == "token_reuse_detected"

    # Verify the entire token family was revoked in DB
    family = RefreshTokenFamily.objects.filter(user=user).first()
    assert family is not None
    assert family.revoked is True
    assert family.revoked_at is not None

    # Now even the legitimate token_2 must be rejected because the lineage was compromised!
    subsequent_resp = client.post(refresh_url, {"refresh": token_2}, format="json")
    assert subsequent_resp.status_code == status.HTTP_401_UNAUTHORIZED
    assert subsequent_resp.json()["error"]["code"] == "token_invalid"


def test_logout_revokes_refresh_token_family():
    client = APIClient()
    user = User.objects.create_user(email="logout@example.com", password="SecurePassword123!")

    login_resp = client.post(
        reverse("accounts:login"),
        {"email": user.email, "password": "SecurePassword123!"},
        format="json",
    )
    access_token = login_resp.json()["access"]
    refresh_token = login_resp.json()["refresh"]

    # Logout
    logout_url = reverse("accounts:logout")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    logout_resp = client.post(logout_url, {"refresh": refresh_token}, format="json")
    assert logout_resp.status_code == status.HTTP_204_NO_CONTENT

    # Attempting to refresh with the logged-out refresh token fails
    refresh_resp = client.post(
        reverse("accounts:refresh"), {"refresh": refresh_token}, format="json"
    )
    assert refresh_resp.status_code == status.HTTP_401_UNAUTHORIZED
