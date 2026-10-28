"""Tests for User and UserManager creation and invariants."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
def test_create_user_with_email_and_password() -> None:
    user = User.objects.create_user(email="testuser@example.com", password="SecurePassword123!")
    assert user.email == "testuser@example.com"
    assert user.is_active is True
    assert user.is_staff is False
    assert user.is_superuser is False
    assert user.check_password("SecurePassword123!") is True
    assert str(user) == "testuser@example.com"


@pytest.mark.django_db
def test_create_user_without_password() -> None:
    user = User.objects.create_user(email="nopass@example.com")
    assert user.has_usable_password() is False


def test_create_user_without_email_raises_value_error() -> None:
    with pytest.raises(ValueError, match="The Email field must be set"):
        User.objects.create_user(email="")


@pytest.mark.django_db
def test_create_superuser_success() -> None:
    admin = User.objects.create_superuser(email="admin@example.com", password="AdminPassword123!")
    assert admin.is_staff is True
    assert admin.is_superuser is True
    assert admin.is_active is True


def test_create_superuser_invalid_flags() -> None:
    with pytest.raises(ValueError, match="Superuser must have is_staff=True"):
        User.objects.create_superuser(email="admin2@example.com", password="pass", is_staff=False)

    with pytest.raises(ValueError, match="Superuser must have is_superuser=True"):
        User.objects.create_superuser(
            email="admin3@example.com", password="pass", is_superuser=False
        )
