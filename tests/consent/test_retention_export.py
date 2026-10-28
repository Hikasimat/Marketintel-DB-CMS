"""Tests for consent export, right-to-erasure, retention cleanup, and aggregation (CON-6)."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.consent.models import (
    ConsentRecord,
    ConsentRecordStatus,
    ConsentType,
    PrivacyPolicyVersion,
    SiteConsentConfig,
)
from apps.consent.tasks import cleanup_expired_consent_records
from apps.sites.models import Site
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole

pytestmark = pytest.mark.django_db


@pytest.fixture
def export_site():
    owner = User.objects.create_user(email="owner@export.com", password="Password123!")
    workspace = Workspace.objects.create(name="Export WS", slug="export-ws")
    WorkspaceMembership.objects.create(workspace=workspace, user=owner, role=WorkspaceRole.OWNER)
    site = Site.objects.create(workspace=workspace, name="Export Site", slug="export-site")
    config = SiteConsentConfig.objects.create(site=site, retention_days=90)
    policy = PrivacyPolicyVersion.objects.create(
        site=site, version="1.0", title="Policy v1.0", is_active=True
    )
    config.active_policy_version = policy
    config.save()
    return {
        "site": site,
        "config": config,
        "policy": policy,
        "workspace": workspace,
        "owner": owner,
    }


def test_visitor_consent_export_gdpr_portability(export_site):
    client = APIClient()
    client.force_authenticate(user=export_site["owner"])
    site = export_site["site"]
    workspace = export_site["workspace"]
    policy = export_site["policy"]

    visitor_id = "visitor-export-target"

    # Create 2 records
    ConsentRecord.objects.create(
        site=site,
        visitor_id=visitor_id,
        policy_version=policy,
        policy_version_string="1.0",
        categories={"necessary": True, "analytics": True},
        status=ConsentRecordStatus.PARTIALLY_GRANTED,
        consent_type=ConsentType.EXPLICIT_OPT_IN,
        expires_at=timezone.now() + timedelta(days=90),
    )
    ConsentRecord.objects.create(
        site=site,
        visitor_id=visitor_id,
        policy_version=policy,
        policy_version_string="1.0",
        categories={"necessary": True, "analytics": False},
        status=ConsentRecordStatus.WITHDRAWN,
        consent_type=ConsentType.WITHDRAWAL,
        withdrawn_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=90),
    )

    url = reverse(
        "consent:consent_record_visitor_export",
        kwargs={
            "workspace_id": workspace.id,
            "site_id": site.id,
            "visitor_id": visitor_id,
        },
    )
    resp = client.get(url)
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["visitor_id"] == visitor_id
    assert len(data["records"]) == 2
    assert data["records"][0]["status"] == ConsentRecordStatus.WITHDRAWN


def test_visitor_consent_purge_gdpr_erasure(export_site):
    client = APIClient()
    client.force_authenticate(user=export_site["owner"])
    site = export_site["site"]
    workspace = export_site["workspace"]
    policy = export_site["policy"]

    visitor_id = "visitor-purge-target"

    ConsentRecord.objects.create(
        site=site,
        visitor_id=visitor_id,
        policy_version=policy,
        policy_version_string="1.0",
        categories={"necessary": True},
        status=ConsentRecordStatus.DENIED,
        expires_at=timezone.now() + timedelta(days=90),
    )
    assert ConsentRecord.objects.filter(site=site, visitor_id=visitor_id).count() == 1

    url = reverse(
        "consent:consent_record_visitor_purge",
        kwargs={
            "workspace_id": workspace.id,
            "site_id": site.id,
            "visitor_id": visitor_id,
        },
    )
    resp = client.delete(url)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["status"] == "PURGED"
    assert resp.json()["records_deleted"] == 1

    # Verify database is clean
    assert ConsentRecord.objects.filter(site=site, visitor_id=visitor_id).count() == 0

    # Verify audit event logged
    audit = AuditEvent.objects.filter(
        workspace_id=workspace.id, action="consent.visitor_records_purged"
    ).first()
    assert audit is not None
    assert audit.payload["records_deleted"] == 1


def test_retention_cleanup_celery_task(export_site):
    site = export_site["site"]
    policy = export_site["policy"]
    now = timezone.now()

    # Expired record (expires_at in past)
    ConsentRecord.objects.create(
        site=site,
        visitor_id="visitor-expired-1",
        policy_version=policy,
        policy_version_string="1.0",
        categories={"necessary": True},
        status=ConsentRecordStatus.GRANTED,
        recorded_at=now - timedelta(days=400),
        expires_at=now - timedelta(days=35),
    )

    # Active record (expires_at in future)
    ConsentRecord.objects.create(
        site=site,
        visitor_id="visitor-active-1",
        policy_version=policy,
        policy_version_string="1.0",
        categories={"necessary": True},
        status=ConsentRecordStatus.GRANTED,
        recorded_at=now,
        expires_at=now + timedelta(days=90),
    )

    assert ConsentRecord.objects.count() == 2

    # Run cleanup task
    result = cleanup_expired_consent_records()
    assert result["status"] == "SUCCESS"
    assert result["deleted_count"] == 1

    assert ConsentRecord.objects.count() == 1
    assert ConsentRecord.objects.first().visitor_id == "visitor-active-1"


def test_consent_summary_metrics(export_site):
    client = APIClient()
    client.force_authenticate(user=export_site["owner"])
    site = export_site["site"]
    workspace = export_site["workspace"]
    policy = export_site["policy"]
    now = timezone.now()

    ConsentRecord.objects.create(
        site=site,
        visitor_id="v1",
        policy_version=policy,
        categories={"necessary": True, "analytics": True, "marketing": False},
        status=ConsentRecordStatus.PARTIALLY_GRANTED,
        expires_at=now + timedelta(days=90),
    )
    ConsentRecord.objects.create(
        site=site,
        visitor_id="v2",
        policy_version=policy,
        categories={"necessary": True, "analytics": False, "marketing": False},
        status=ConsentRecordStatus.DENIED,
        expires_at=now + timedelta(days=90),
    )

    url = reverse(
        "consent:consent_summary",
        kwargs={"workspace_id": workspace.id, "site_id": site.id},
    )
    resp = client.get(url)
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert data["total_decisions"] == 2
    assert data["partially_granted_count"] == 1
    assert data["denied_count"] == 1
    assert data["category_acceptance_rates"]["analytics"] == 50.0
    assert data["category_acceptance_rates"]["necessary"] == 100.0
