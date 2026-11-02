"""URL configuration for Google Ads workspace integration."""

from __future__ import annotations

from django.urls import path

from apps.google_ads.views import (
    GoogleAdsAdGroupsView,
    GoogleAdsAuditLogListView,
    GoogleAdsAuthorizeView,
    GoogleAdsCallbackView,
    GoogleAdsCampaignBudgetView,
    GoogleAdsCampaignPauseView,
    GoogleAdsCampaignResumeView,
    GoogleAdsCampaignsView,
    GoogleAdsConnectionDetailView,
    GoogleAdsCustomerListView,
    GoogleAdsCustomerSelectView,
    GoogleAdsDisconnectView,
    GoogleAdsKeywordsView,
)

urlpatterns = [
    path("connection/", GoogleAdsConnectionDetailView.as_view(), name="google-ads-connection"),
    path("authorize/", GoogleAdsAuthorizeView.as_view(), name="google-ads-authorize"),
    path("callback/", GoogleAdsCallbackView.as_view(), name="google-ads-callback"),
    path("disconnect/", GoogleAdsDisconnectView.as_view(), name="google-ads-disconnect"),
    path("customers/", GoogleAdsCustomerListView.as_view(), name="google-ads-customers"),
    path(
        "customers/select/",
        GoogleAdsCustomerSelectView.as_view(),
        name="google-ads-customers-select",
    ),
    path("campaigns/", GoogleAdsCampaignsView.as_view(), name="google-ads-campaigns"),
    path(
        "campaigns/<str:campaign_id>/pause/",
        GoogleAdsCampaignPauseView.as_view(),
        name="google-ads-campaign-pause",
    ),
    path(
        "campaigns/<str:campaign_id>/resume/",
        GoogleAdsCampaignResumeView.as_view(),
        name="google-ads-campaign-resume",
    ),
    path(
        "campaigns/<str:campaign_id>/budget/",
        GoogleAdsCampaignBudgetView.as_view(),
        name="google-ads-campaign-budget",
    ),
    path("ad-groups/", GoogleAdsAdGroupsView.as_view(), name="google-ads-ad-groups"),
    path("keywords/", GoogleAdsKeywordsView.as_view(), name="google-ads-keywords"),
    path("audit-logs/", GoogleAdsAuditLogListView.as_view(), name="google-ads-audit-logs"),
]
