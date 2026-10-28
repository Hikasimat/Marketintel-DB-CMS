"""URL routing for consent management and public browser contracts."""

from __future__ import annotations

from django.urls import path

from apps.consent.views import (
    ConsentRecordListView,
    ConsentRecordVisitorExportView,
    ConsentRecordVisitorPurgeView,
    ConsentSummaryView,
    PrivacyPolicyVersionActivateView,
    PrivacyPolicyVersionDetailView,
    PrivacyPolicyVersionListView,
    PublicBannerConfigView,
    PublicConsentStatusView,
    PublicConsentSubmitView,
    PublicConsentWithdrawView,
    SiteConsentConfigView,
)

app_name = "consent"

urlpatterns = [
    # Workspace-scoped management routes
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/consent/config/",
        SiteConsentConfigView.as_view(),
        name="site_consent_config",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/consent/versions/",
        PrivacyPolicyVersionListView.as_view(),
        name="privacy_policy_version_list_create",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/consent/versions/<uuid:version_id>/",
        PrivacyPolicyVersionDetailView.as_view(),
        name="privacy_policy_version_detail",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/consent/versions/<uuid:version_id>/activate/",
        PrivacyPolicyVersionActivateView.as_view(),
        name="privacy_policy_version_activate",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/consent/records/",
        ConsentRecordListView.as_view(),
        name="consent_record_list",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/consent/records/visitor/<str:visitor_id>/",
        ConsentRecordVisitorPurgeView.as_view(),
        name="consent_record_visitor_purge",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/consent/records/visitor/<str:visitor_id>/export/",
        ConsentRecordVisitorExportView.as_view(),
        name="consent_record_visitor_export",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/consent/summary/",
        ConsentSummaryView.as_view(),
        name="consent_summary",
    ),
    # Public browser / SDK contracts (CT-6 Origin checked)
    path(
        "public/sites/<slug:site_slug>/consent-config",
        PublicBannerConfigView.as_view(),
        name="public_consent_config",
    ),
    path(
        "public/sites/<slug:site_slug>/consent/banner-config",
        PublicBannerConfigView.as_view(),
        name="public_banner_config",
    ),
    path(
        "public/sites/<slug:site_slug>/consent",
        PublicConsentSubmitView.as_view(),
        name="public_consent_submit",
    ),
    path(
        "public/sites/<slug:site_slug>/consent/withdraw",
        PublicConsentWithdrawView.as_view(),
        name="public_consent_withdraw",
    ),
    path(
        "public/sites/<slug:site_slug>/consent/status",
        PublicConsentStatusView.as_view(),
        name="public_consent_status",
    ),
]
