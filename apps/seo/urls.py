"""URL patterns for SEO management and public SEO feeds."""

from django.urls import path

from apps.seo.views import (
    ArticleSEOView,
    PublicArticleSEOView,
    PublicRobotsTxtView,
    PublicSitemapXmlView,
    RedirectRuleDetailView,
    RedirectRuleListCreateView,
    SEOAuditView,
    SiteSEOSettingsView,
)

app_name = "seo"

urlpatterns = [
    # Management endpoints
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/seo/",
        SiteSEOSettingsView.as_view(),
        name="site_seo_settings",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/articles/<uuid:article_id>/seo/",
        ArticleSEOView.as_view(),
        name="article_seo",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/redirects/",
        RedirectRuleListCreateView.as_view(),
        name="redirect_rule_list_create",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/redirects/<uuid:rule_id>/",
        RedirectRuleDetailView.as_view(),
        name="redirect_rule_detail",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/seo-audit/",
        SEOAuditView.as_view(),
        name="seo_audit",
    ),
    # Public endpoints
    path(
        "public/sites/<slug:site_slug>/sitemap.xml",
        PublicSitemapXmlView.as_view(),
        name="public_sitemap",
    ),
    path(
        "public/sites/<slug:site_slug>/robots.txt",
        PublicRobotsTxtView.as_view(),
        name="public_robots_txt",
    ),
    path(
        "public/sites/<slug:site_slug>/articles/<slug:article_slug>/seo/",
        PublicArticleSEOView.as_view(),
        name="public_article_seo",
    ),
]
