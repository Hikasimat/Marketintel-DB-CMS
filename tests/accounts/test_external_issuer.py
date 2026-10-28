"""Tests for ExternalIssuerAuthentication adapter (AUTH-5 boundary)."""

import time

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.common.jwt import encode_jwt

pytestmark = pytest.mark.django_db

EXTERNAL_SECRET = "external-idp-secret-key-boundary-test-12345"
EXTERNAL_ISSUER_CONFIG = {
    "marketintel": {
        "secret": EXTERNAL_SECRET,
        "issuer": "https://auth.marketintel.internal",
        "audience": "cms-backend",
    }
}


@override_settings(EXTERNAL_AUTH_ISSUERS=EXTERNAL_ISSUER_CONFIG)
def test_external_issuer_authentication_success_provisions_user():
    client = APIClient()
    now = int(time.time())

    # External token issued by MarketIntel / External IdP
    token = encode_jwt(
        {
            "sub": "marketintel-ext-user-999",
            "email": "external.analyst@marketintel.com",
            "iss": "https://auth.marketintel.internal",
            "aud": "cms-backend",
            "iat": now,
            "exp": now + 3600,
        },
        secret=EXTERNAL_SECRET,
    )

    url = reverse("accounts:current_user")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    response = client.get(url)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["email"] == "external.analyst@marketintel.com"

    # Verify user was created in local database without direct model coupling
    user = User.objects.get(email="external.analyst@marketintel.com")
    assert user.is_active is True


@override_settings(EXTERNAL_AUTH_ISSUERS=EXTERNAL_ISSUER_CONFIG)
def test_external_issuer_authentication_fails_on_wrong_issuer():
    client = APIClient()
    now = int(time.time())

    token = encode_jwt(
        {
            "sub": "unknown",
            "email": "attacker@evil.com",
            "iss": "https://evil-issuer.com",
            "aud": "cms-backend",
            "iat": now,
            "exp": now + 3600,
        },
        secret=EXTERNAL_SECRET,
    )

    url = reverse("accounts:current_user")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    response = client.get(url)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@override_settings(EXTERNAL_AUTH_ISSUERS=EXTERNAL_ISSUER_CONFIG)
def test_external_issuer_authentication_fails_on_expired_token():
    client = APIClient()
    past = int(time.time()) - 100

    token = encode_jwt(
        {
            "sub": "expired",
            "email": "expired@marketintel.com",
            "iss": "https://auth.marketintel.internal",
            "aud": "cms-backend",
            "iat": past - 3600,
            "exp": past,
        },
        secret=EXTERNAL_SECRET,
    )

    url = reverse("accounts:current_user")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    response = client.get(url)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
