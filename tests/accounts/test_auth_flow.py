"""Tests for authentication flows, password validation, and user profile."""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.validators import PasswordComplexityValidator
from apps.common.jwt import encode_jwt

pytestmark = pytest.mark.django_db


def test_password_complexity_validator():
    validator = PasswordComplexityValidator(min_length=12)

    # Valid complex password
    validator.validate("StrongP@ssw0rd!123")

    # Too short
    with pytest.raises(ValidationError, match="at least 12 characters"):
        validator.validate("Short1!Aa")

    # Missing uppercase
    with pytest.raises(ValidationError, match="uppercase letter"):
        validator.validate("weakpassw0rd!123")

    # Missing lowercase
    with pytest.raises(ValidationError, match="lowercase letter"):
        validator.validate("WEAKPASSW0RD!123")

    # Missing digit
    with pytest.raises(ValidationError, match="numerical digit"):
        validator.validate("NoDigitsHere!@#$")

    # Missing symbol
    with pytest.raises(ValidationError, match="special symbol"):
        validator.validate("NoSymbols123456")


def test_login_success_and_token_issuance():
    client = APIClient()
    email = "editor@example.com"
    password = "SecurePassword123!"
    User.objects.create_user(email=email, password=password)

    url = reverse("accounts:login")
    response = client.post(url, {"email": email, "password": password}, format="json")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access" in data
    assert "refresh" in data
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] == 900


def test_login_invalid_password_returns_400():
    client = APIClient()
    email = "editor@example.com"
    User.objects.create_user(email=email, password="SecurePassword123!")

    url = reverse("accounts:login")
    response = client.post(url, {"email": email, "password": "WrongPassword123!"}, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "validation_error"


def test_login_inactive_user_returns_400():
    client = APIClient()
    email = "inactive@example.com"
    user = User.objects.create_user(email=email, password="SecurePassword123!")
    user.is_active = False
    user.save()

    url = reverse("accounts:login")
    response = client.post(url, {"email": email, "password": "SecurePassword123!"}, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_current_user_me_endpoint_requires_auth():
    client = APIClient()
    url = reverse("accounts:current_user")
    response = client.get(url)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    data = response.json()
    assert data["error"]["code"] in ("not_authenticated", "authentication_failed")


def test_current_user_me_endpoint_with_valid_jwt():
    client = APIClient()
    user = User.objects.create_user(email="user@example.com", password="SecurePassword123!")

    # Login to get valid token
    login_url = reverse("accounts:login")
    login_resp = client.post(
        login_url, {"email": "user@example.com", "password": "SecurePassword123!"}, format="json"
    )
    access_token = login_resp.json()["access"]

    # Call /api/v1/auth/me/
    url = reverse("accounts:current_user")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    response = client.get(url)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == str(user.id)
    assert data["email"] == user.email


def test_current_user_with_expired_token_returns_401():
    from django.conf import settings

    client = APIClient()
    user = User.objects.create_user(email="expired@example.com", password="SecurePassword123!")

    # Fabricate an expired access token
    expired_token = encode_jwt(
        {
            "sub": str(user.id),
            "type": "access",
            "iss": "cms-backend",
            "aud": "cms-api",
            "exp": 1000,
        },
        secret=settings.SECRET_KEY,
    )

    url = reverse("accounts:current_user")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {expired_token}")
    response = client.get(url)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    data = response.json()
    assert data["error"]["code"] == "token_expired"
