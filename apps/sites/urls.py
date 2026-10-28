"""URL routing for Sites and Domains within workspaces."""

from django.urls import path

from apps.sites.views import (
    DomainDetailView,
    DomainListCreateView,
    DomainVerifyView,
    SiteDetailView,
    SiteListCreateView,
)

app_name = "sites"

urlpatterns = [
    path(
        "workspaces/<uuid:workspace_id>/sites/",
        SiteListCreateView.as_view(),
        name="site_list_create",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/",
        SiteDetailView.as_view(),
        name="site_detail",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/domains/",
        DomainListCreateView.as_view(),
        name="domain_list_create",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/domains/<uuid:domain_id>/",
        DomainDetailView.as_view(),
        name="domain_detail",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/domains/<uuid:domain_id>/verify/",
        DomainVerifyView.as_view(),
        name="domain_verify",
    ),
]
