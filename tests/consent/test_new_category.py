"""Tests verifying that adding a new optional category never silently enables it (CON-5)."""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.consent.models import PrivacyPolicyVersion, SiteConsentConfig
from apps.sites.models import Site
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole

pytestmark = pytest.mark.django_db


@pytest.fixture
def new_cat_site():
    owner = User.objects.create_user(email="owner@newcat.com", password="Password123!")
    workspace = Workspace.objects.create(name="NewCat WS", slug="newcat-ws")
    WorkspaceMembership.objects.create(workspace=workspace, user=owner, role=WorkspaceRole.OWNER)
    site = Site.objects.create(
        workspace=workspace,
        name="NewCat Site",
        slug="newcat-site",
        allowed_origins=["https://site.com"],
    )
    config = SiteConsentConfig.objects.create(site=site)
    version = PrivacyPolicyVersion.objects.create(
        site=site,
        version="1.0",
        title="Policy v1.0",
        is_active=True,
    )
    config.active_policy_version = version
    config.save()
    return {"site": site, "config": config, "workspace": workspace, "owner": owner}


def test_adding_new_category_never_silently_enables_it(new_cat_site):
    client = APIClient()
    workspace = new_cat_site["workspace"]
    site = new_cat_site["site"]
    config = new_cat_site["config"]
    owner = new_cat_site["owner"]

    # 1. Existing visitor consents to all current categories
    visitor_id = "visitor-existing-user"
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

    # 2. Site admin adds a new custom category 'social_media'
    # Even if admin attempts to smuggle default_state=True or required=True:
    client.force_authenticate(user=owner)
    config_url = reverse(
        "consent:site_consent_config",
        kwargs={"workspace_id": workspace.id, "site_id": site.id},
    )
    patch_resp = client.patch(
        config_url,
        {
            "categories": {
                "social_media": {
                    "title": "Social Media Sharing",
                    "description": "Enables interactive widgets and third-party content embeds.",
                    "default_state": True,  # Malicious/invalid attempt to enable by default
                    "required": True,  # Malicious/invalid attempt to make optional required
                }
            }
        },
        format="json",
    )
    assert patch_resp.status_code == status.HTTP_200_OK

    # Verify model clean() and get_all_categories() neutralized it
    config.refresh_from_db()
    all_cats = config.get_all_categories()
    assert "social_media" in all_cats
    assert all_cats["social_media"]["required"] is False
    assert all_cats["social_media"]["default_state"] is False

    # 3. Check public banner config
    client.logout()
    banner_url = reverse("consent:public_banner_config", kwargs={"site_slug": site.slug})
    b_resp = client.get(banner_url, HTTP_ORIGIN="https://site.com")
    assert b_resp.status_code == status.HTTP_200_OK
    b_data = b_resp.json()
    assert b_data["categories"]["social_media"]["default_state"] is False
    assert b_data["default_states"]["social_media"] is False

    # 4. Existing visitor status check: social_media must be FALSE (not silently enabled)
    status_url = reverse("consent:public_consent_status", kwargs={"site_slug": site.slug})
    s_resp = client.get(f"{status_url}?visitor_id={visitor_id}", HTTP_ORIGIN="https://site.com")
    assert s_resp.status_code == status.HTTP_200_OK
    # Because 'social_media' was not in the visitor's record, it is NOT granted
    assert s_resp.json()["categories"].get("social_media") is not True

    # 5. Visitor can now explicitly consent to social_media if desired
    client.post(
        submit_url,
        {
            "visitor_id": visitor_id,
            "categories": {
                "necessary": True,
                "analytics": True,
                "marketing": True,
                "preferences": True,
                "social_media": True,
            },
        },
        format="json",
        HTTP_ORIGIN="https://site.com",
    )

    s_resp2 = client.get(f"{status_url}?visitor_id={visitor_id}", HTTP_ORIGIN="https://site.com")
    assert s_resp2.json()["categories"]["social_media"] is True
