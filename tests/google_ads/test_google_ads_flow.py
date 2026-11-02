"""Comprehensive tests for Google Ads OAuth, reporting, mutations,
confirmation, and multi-tenant isolation.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.google_ads.models import GoogleAdsCampaignAuditLog, GoogleAdsConnection
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole

pytestmark = pytest.mark.django_db


@pytest.fixture
def google_ads_setup() -> dict[str, object]:
    user = User.objects.create_user(email="adsowner@example.com", password="Password123!")
    workspace = Workspace.objects.create(name="Ads Workspace", slug="ads-workspace")
    WorkspaceMembership.objects.create(workspace=workspace, user=user, role=WorkspaceRole.OWNER)

    other_user = User.objects.create_user(email="stranger@example.com", password="Password123!")
    other_workspace = Workspace.objects.create(name="Other Workspace", slug="other-workspace")
    WorkspaceMembership.objects.create(
        workspace=other_workspace, user=other_user, role=WorkspaceRole.OWNER
    )

    return {
        "user": user,
        "workspace": workspace,
        "other_user": other_user,
        "other_workspace": other_workspace,
    }


def test_google_ads_authorize_and_callback(google_ads_setup: dict[str, object]) -> None:
    client = APIClient()
    user = google_ads_setup["user"]
    workspace = google_ads_setup["workspace"]
    assert isinstance(workspace, Workspace)

    client.force_authenticate(user=user)

    # 1. Authorize
    auth_url = f"/api/v1/workspaces/{workspace.id}/google-ads/authorize/"
    resp = client.get(auth_url)
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()
    assert "authorization_url" in data
    assert "accounts.google.com" in data["authorization_url"]
    assert "adwords" in data["authorization_url"]

    # 2. Callback
    cb_url = f"/api/v1/workspaces/{workspace.id}/google-ads/callback/"
    cb_resp = client.post(
        cb_url,
        {
            "code": "mock-ads-code-123",
            "redirect_uri": "https://example.com/callback",
            "developer_token": "my-dev-token",
        },
        format="json",
    )
    assert cb_resp.status_code == status.HTTP_200_OK

    conn = GoogleAdsConnection.objects.get(workspace=workspace)
    assert conn.is_active is True
    assert conn.status == "CONNECTED"
    creds = conn.get_credentials()
    assert "mock-token-mock-ads-code-123" in creds.get("access_token", "")
    assert conn.get_developer_token() == "my-dev-token"


def test_customer_selection_and_listing(google_ads_setup: dict[str, object]) -> None:
    client = APIClient()
    user = google_ads_setup["user"]
    workspace = google_ads_setup["workspace"]
    assert isinstance(workspace, Workspace)

    conn = GoogleAdsConnection.objects.create(workspace=workspace, is_active=True)
    conn.set_credentials({"access_token": "valid-token"})
    conn.save()

    client.force_authenticate(user=user)

    # 1. List accessible customers (mocked adapter)
    with patch(
        "apps.google_ads.adapters.google_ads.GoogleAdsAdapter.list_accessible_customers",
        return_value=["customers/1234567890", "customers/9876543210"],
    ):
        list_url = f"/api/v1/workspaces/{workspace.id}/google-ads/customers/"
        resp = client.get(list_url)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["count"] == 2
        assert "1234567890" in data["customers"]

    # 2. Customer select validation failure (not 10 digits)
    select_url = f"/api/v1/workspaces/{workspace.id}/google-ads/customers/select/"
    bad_resp = client.post(select_url, {"customer_id": "123"}, format="json")
    assert bad_resp.status_code == status.HTTP_400_BAD_REQUEST

    # 3. Valid customer select
    good_resp = client.post(
        select_url,
        {"customer_id": "123-456-7890", "manager_customer_id": "999-888-7777"},
        format="json",
    )
    assert good_resp.status_code == status.HTTP_200_OK
    conn.refresh_from_db()
    assert conn.customer_id == "1234567890"
    assert conn.manager_customer_id == "9998887777"


def test_gaql_reporting_campaigns_adgroups_keywords(
    google_ads_setup: dict[str, object],
) -> None:
    client = APIClient()
    user = google_ads_setup["user"]
    workspace = google_ads_setup["workspace"]
    assert isinstance(workspace, Workspace)

    conn = GoogleAdsConnection.objects.create(
        workspace=workspace, customer_id="1234567890", is_active=True
    )
    conn.set_credentials({"access_token": "valid-token"})
    conn.save()

    client.force_authenticate(user=user)

    # Campaigns
    with patch(
        "apps.google_ads.adapters.google_ads.GoogleAdsAdapter.get_campaigns",
        return_value=[
            {
                "campaign_id": "1001",
                "campaign_name": "Search Brand",
                "status": "ENABLED",
                "budget_amount": 50.0,
                "impressions": 1000,
                "clicks": 50,
                "cost": 25.0,
                "conversions": 5.0,
                "ctr": 0.05,
                "average_cpc": 0.50,
            }
        ],
    ):
        c_url = f"/api/v1/workspaces/{workspace.id}/google-ads/campaigns/"
        resp = client.get(c_url)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["count"] == 1
        assert data["campaigns"][0]["campaign_name"] == "Search Brand"

    # Ad Groups
    with patch(
        "apps.google_ads.adapters.google_ads.GoogleAdsAdapter.get_ad_groups",
        return_value=[
            {
                "ad_group_id": "2001",
                "ad_group_name": "Exact Match",
                "status": "ENABLED",
                "campaign_id": "1001",
                "campaign_name": "Search Brand",
                "impressions": 500,
                "clicks": 25,
                "cost": 12.5,
                "conversions": 2.0,
                "ctr": 0.05,
            }
        ],
    ):
        ag_url = f"/api/v1/workspaces/{workspace.id}/google-ads/ad-groups/"
        resp = client.get(ag_url)
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["count"] == 1

    # Keywords
    with patch(
        "apps.google_ads.adapters.google_ads.GoogleAdsAdapter.get_keywords",
        return_value=[
            {
                "criterion_id": "3001",
                "keyword_text": "market intelligence tool",
                "match_type": "EXACT",
                "status": "ENABLED",
                "impressions": 200,
                "clicks": 10,
                "cost": 5.0,
                "conversions": 1.0,
                "average_cpc": 0.5,
            }
        ],
    ):
        kw_url = f"/api/v1/workspaces/{workspace.id}/google-ads/keywords/"
        resp = client.get(kw_url)
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["count"] == 1


def test_mutations_confirmation_and_audit_logging(google_ads_setup: dict[str, object]) -> None:
    client = APIClient()
    user = google_ads_setup["user"]
    workspace = google_ads_setup["workspace"]
    assert isinstance(workspace, Workspace)
    assert isinstance(user, User)

    conn = GoogleAdsConnection.objects.create(
        workspace=workspace, customer_id="1234567890", is_active=True
    )
    conn.set_credentials({"access_token": "valid-token"})
    conn.save()

    client.force_authenticate(user=user)

    pause_url = f"/api/v1/workspaces/{workspace.id}/google-ads/campaigns/1001/pause/"

    # 1. Mutation rejected when confirm is missing or False
    unconfirmed_resp = client.post(pause_url, {"confirm": False}, format="json")
    assert unconfirmed_resp.status_code == status.HTTP_400_BAD_REQUEST

    missing_confirm_resp = client.post(pause_url, {}, format="json")
    assert missing_confirm_resp.status_code == status.HTTP_400_BAD_REQUEST

    # 2. Successful Pause with confirm=True
    with patch(
        "apps.google_ads.adapters.google_ads.GoogleAdsAdapter.set_campaign_status",
        return_value={"status": "SUCCESS", "campaign_id": "1001", "new_status": "PAUSED"},
    ):
        pause_resp = client.post(
            pause_url,
            {"confirm": True, "campaign_name": "Brand Campaign"},
            format="json",
        )
        assert pause_resp.status_code == status.HTTP_200_OK
        assert pause_resp.json()["status"] == "PAUSED"

    # Verify audit log was created
    audit_log = GoogleAdsCampaignAuditLog.objects.filter(
        connection=conn, campaign_id="1001", action=GoogleAdsCampaignAuditLog.Action.CAMPAIGN_PAUSE
    ).first()
    assert audit_log is not None
    assert audit_log.performed_by == user
    assert audit_log.campaign_name == "Brand Campaign"

    # 3. Successful Resume with confirm=True
    resume_url = f"/api/v1/workspaces/{workspace.id}/google-ads/campaigns/1001/resume/"
    with patch(
        "apps.google_ads.adapters.google_ads.GoogleAdsAdapter.set_campaign_status",
        return_value={"status": "SUCCESS", "campaign_id": "1001", "new_status": "ENABLED"},
    ):
        resume_resp = client.post(
            resume_url,
            {"confirm": True, "campaign_name": "Brand Campaign"},
            format="json",
        )
        assert resume_resp.status_code == status.HTTP_200_OK
        assert resume_resp.json()["status"] == "ENABLED"

    assert GoogleAdsCampaignAuditLog.objects.filter(
        connection=conn,
        campaign_id="1001",
        action=GoogleAdsCampaignAuditLog.Action.CAMPAIGN_RESUME,
    ).exists()

    # 4. Successful Budget Update with confirm=True
    budget_url = f"/api/v1/workspaces/{workspace.id}/google-ads/campaigns/1001/budget/"
    with patch(
        "apps.google_ads.adapters.google_ads.GoogleAdsAdapter.update_campaign_budget",
        return_value={
            "status": "SUCCESS",
            "resource_name": "customers/1234567890/campaignBudgets/5001",
            "amount_micros": 20_000_000,
        },
    ):
        budget_resp = client.post(
            budget_url,
            {
                "budget_resource_name": "customers/1234567890/campaignBudgets/5001",
                "amount_micros": 20_000_000,
                "confirm": True,
            },
            format="json",
        )
        assert budget_resp.status_code == status.HTTP_200_OK
        assert budget_resp.json()["status"] == "UPDATED"

    # Verify audit log listing endpoint
    logs_url = f"/api/v1/workspaces/{workspace.id}/google-ads/audit-logs/"
    logs_resp = client.get(logs_url)
    assert logs_resp.status_code == status.HTTP_200_OK
    assert logs_resp.json()["count"] == 3


def test_multi_tenant_workspace_isolation(google_ads_setup: dict[str, object]) -> None:
    client = APIClient()
    workspace = google_ads_setup["workspace"]
    other_user = google_ads_setup["other_user"]
    assert isinstance(workspace, Workspace)

    # other_user has no membership in `workspace`
    client.force_authenticate(user=other_user)

    url = f"/api/v1/workspaces/{workspace.id}/google-ads/authorize/"
    resp = client.get(url)
    assert resp.status_code == status.HTTP_403_FORBIDDEN
