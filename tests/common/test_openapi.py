"""OpenAPI schema generation tests (FND-3)."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient


@pytest.mark.req("FND-3")
def test_schema_endpoint_generates_openapi_spec() -> None:
    client = APIClient()
    response = client.get("/api/v1/schema/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.oai.openapi")
    content = response.content.decode("utf-8")
    assert "openapi: 3." in content
    assert "Headless CMS API" in content
    assert "/health/live" in content or "paths:" in content


@pytest.mark.req("FND-3")
def test_interactive_docs_ui_rendered_when_enabled() -> None:
    client = APIClient()
    response = client.get("/api/v1/docs/")
    assert response.status_code == 200
    assert b"swagger-ui" in response.content.lower()
