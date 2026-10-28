"""Health and readiness probe tests (FND-2)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from rest_framework.test import APIClient


@pytest.mark.req("FND-2")
def test_liveness_probe_returns_200() -> None:
    client = APIClient()
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "live"}
    assert "X-Request-ID" in response.headers


@pytest.mark.req("FND-2")
@pytest.mark.django_db
def test_readiness_probe_returns_200_when_healthy() -> None:
    client = APIClient()
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.mark.req("FND-2")
def test_readiness_probe_returns_503_without_leaking_details_when_db_down() -> None:
    client = APIClient()
    with patch(
        "django.db.connection.cursor",
        side_effect=Exception("Database password failed or connection lost"),
    ):
        response = client.get("/health/ready")

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "not_ready"
    assert "database" in data["unhealthy"]
    # Check that exception message is not leaked
    assert "password" not in str(data)
    assert "connection lost" not in str(data)
