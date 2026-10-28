"""Tests for audit trail immutability, redaction, and API inspection."""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.audit.services import record_audit_event
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole

pytestmark = pytest.mark.django_db


def test_audit_event_immutability():
    event = AuditEvent.objects.create(
        action="test.action",
        resource_type="test",
        resource_id="123",
        payload={"info": "initial"},
    )

    # Attempt to update should raise RuntimeError
    event.action = "tampered.action"
    with pytest.raises(RuntimeError, match="immutable and cannot be updated"):
        event.save()

    # Attempt to delete should raise RuntimeError
    with pytest.raises(RuntimeError, match="immutable and cannot be deleted"):
        event.delete()


def test_record_audit_event_redacts_sensitive_payload():
    event = record_audit_event(
        action="user.login_attempt",
        resource_type="auth",
        resource_id="1",
        payload={
            "email": "user@example.com",
            "password": "SuperSecretPassword123!",
            "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy",
            "nested": {"api_key": "secret-api-key-999", "safe_param": "hello"},
        },
    )

    assert event.payload["email"] == "user@example.com"
    assert event.payload["password"] == "[REDACTED]"
    assert event.payload["token"] == "[REDACTED]"
    assert event.payload["nested"]["api_key"] == "[REDACTED]"
    assert event.payload["nested"]["safe_param"] == "hello"


def test_workspace_audit_log_endpoint_rbac():
    client = APIClient()
    owner = User.objects.create_user(email="owner@example.com", password="SecurePassword123!")
    editor = User.objects.create_user(email="editor@example.com", password="SecurePassword123!")

    workspace = Workspace.objects.create(name="Audit WS", slug="audit-ws")
    WorkspaceMembership.objects.create(workspace=workspace, user=owner, role=WorkspaceRole.OWNER)
    WorkspaceMembership.objects.create(workspace=workspace, user=editor, role=WorkspaceRole.EDITOR)

    # Record an audit event
    record_audit_event(
        action="site.created",
        workspace_id=workspace.id,
        actor=owner,
        resource_type="site",
        resource_id="site-1",
    )

    url = reverse("audit:workspace_audit_logs", kwargs={"workspace_id": workspace.id})

    # Editor lacks admin role -> 403 Forbidden
    client.force_authenticate(user=editor)
    assert client.get(url).status_code == status.HTTP_403_FORBIDDEN

    # Owner has admin+ role -> 200 OK
    client.force_authenticate(user=owner)
    response = client.get(url)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["count"] >= 1
    assert data["results"][0]["action"] == "site.created"
