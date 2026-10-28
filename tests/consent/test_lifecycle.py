"""Tests for consent withdrawal and policy version bump invalidation lifecycle (CON-4)."""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.consent.models import (
    ConsentRecord,
    ConsentRecordStatus,
    PrivacyPolicyVersion,
    SiteConsentConfig,
)
from apps.sites.models import Site
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole

pytestmark = pytest.mark.django_db


@pytest.fixture
def lifecycle_site():
    owner = User.objects.create_user(email="owner@lifecycle.com", password="Password123!")
    workspace = Workspace.objects.create(name="Life WS", slug="life-ws")
    WorkspaceMembership.objects.create(workspace=workspace, user=owner, role=WorkspaceRole.OWNER)
    site = Site.objects.create(
        workspace=workspace,
        name="Lifecycle Site",
        slug="lifecycle-site",
        allowed_origins=["https://site.com"],
    )
    config = SiteConsentConfig.objects.create(
        site=site,
        jurisdiction_mode="GDPR",
        gcm_enabled=True,
    )
    v1 = PrivacyPolicyVersion.objects.create(
        site=site,
        version="1.0",
        title="Privacy Policy v1.0",
        is_active=True,
    )
    config.active_policy_version = v1
    config.save()
    return {"site": site, "config": config, "v1": v1, "workspace": workspace, "owner": owner}


def test_consent_withdrawal_preserves_history_and_disables_optional(lifecycle_site):
    client = APIClient()
    site = lifecycle_site["site"]
    visitor_id = "visitor-withdraw-123"

    # 1. Record initial opt-in
    submit_url = reverse("consent:public_consent_submit", kwargs={"site_slug": site.slug})
    client.post(
        submit_url,
        {
            "visitor_id": visitor_id,
            "categories": {
                "necessary": True,
                "analytics": True,
                "marketing": True,
                "preferences": True,
            },
        },
        format="json",
        HTTP_ORIGIN="https://site.com",
    )

    initial_record = ConsentRecord.objects.get(site=site, visitor_id=visitor_id)
    assert initial_record.status == ConsentRecordStatus.GRANTED

    # 2. Withdraw consent
    withdraw_url = reverse("consent:public_consent_withdraw", kwargs={"site_slug": site.slug})
    withdraw_resp = client.post(
        withdraw_url,
        {"visitor_id": visitor_id},
        format="json",
        HTTP_ORIGIN="https://site.com",
    )
    assert withdraw_resp.status_code == status.HTTP_200_OK
    data = withdraw_resp.json()
    assert data["status"] == "WITHDRAWN"
    assert data["categories"]["necessary"] is True
    assert data["categories"]["analytics"] is False
    assert data["categories"]["marketing"] is False
    assert data["gcm_update"]["analytics_storage"] == "denied"
    assert data["gcm_update"]["ad_storage"] == "denied"

    # 3. Verify history is preserved (now two records exist)
    records = list(
        ConsentRecord.objects.filter(site=site, visitor_id=visitor_id).order_by("recorded_at")
    )
    assert len(records) == 2
    assert records[0].status == ConsentRecordStatus.WITHDRAWN  # Prior marked withdrawn
    assert records[0].withdrawn_at is not None
    assert records[1].status == ConsentRecordStatus.WITHDRAWN  # New withdrawal record

    # 4. Query status
    status_url = reverse("consent:public_consent_status", kwargs={"site_slug": site.slug})
    status_resp = client.get(
        f"{status_url}?visitor_id={visitor_id}", HTTP_ORIGIN="https://site.com"
    )
    assert status_resp.status_code == status.HTTP_200_OK
    status_data = status_resp.json()
    assert status_data["is_withdrawn"] is True
    assert status_data["requires_reconsent"] is True
    assert status_data["categories"]["analytics"] is False


def test_policy_version_bump_invalidates_prior_consent(lifecycle_site):
    client = APIClient()
    site = lifecycle_site["site"]
    workspace = lifecycle_site["workspace"]
    visitor_id = "visitor-policy-bump"

    # 1. Visitor consents under v1.0
    submit_url = reverse("consent:public_consent_submit", kwargs={"site_slug": site.slug})
    client.post(
        submit_url,
        {
            "visitor_id": visitor_id,
            "policy_version": "1.0",
            "categories": {"necessary": True, "analytics": True, "marketing": False},
        },
        format="json",
        HTTP_ORIGIN="https://site.com",
    )

    # Status under v1.0
    status_url = reverse("consent:public_consent_status", kwargs={"site_slug": site.slug})
    s_resp = client.get(f"{status_url}?visitor_id={visitor_id}", HTTP_ORIGIN="https://site.com")
    assert s_resp.json()["requires_reconsent"] is False
    assert s_resp.json()["categories"]["analytics"] is True

    # 2. Site creates and activates v2.0
    client.force_authenticate(user=lifecycle_site["owner"])
    v2_create_url = reverse(
        "consent:privacy_policy_version_list_create",
        kwargs={"workspace_id": workspace.id, "site_id": site.id},
    )
    v2_resp = client.post(
        v2_create_url,
        {
            "version": "2.0",
            "title": "Privacy Policy v2.0 - Material Updates",
            "activate_now": True,
        },
        format="json",
    )
    assert v2_resp.status_code == status.HTTP_201_CREATED

    # 3. Query visitor status without auth (public)
    client.logout()
    s_resp2 = client.get(f"{status_url}?visitor_id={visitor_id}", HTTP_ORIGIN="https://site.com")
    assert s_resp2.status_code == status.HTTP_200_OK
    s2_data = s_resp2.json()

    # Crucial CON-4 requirement: Policy version bump invalidates
    # prior consent for optional categories
    assert s2_data["requires_reconsent"] is True
    assert s2_data["categories"]["analytics"] is False  # Suppressed!
    assert s2_data["categories"]["necessary"] is True

    # 4. Visitor consents to new version v2.0
    client.post(
        submit_url,
        {
            "visitor_id": visitor_id,
            "policy_version": "2.0",
            "categories": {"necessary": True, "analytics": True, "marketing": True},
        },
        format="json",
        HTTP_ORIGIN="https://site.com",
    )

    s_resp3 = client.get(f"{status_url}?visitor_id={visitor_id}", HTTP_ORIGIN="https://site.com")
    assert s_resp3.json()["requires_reconsent"] is False
    assert s_resp3.json()["categories"]["analytics"] is True
    assert s_resp3.json()["categories"]["marketing"] is True
