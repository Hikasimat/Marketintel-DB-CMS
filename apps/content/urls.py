"""URL routing for Article management and public content delivery."""

from django.urls import path

from apps.content.views import (
    ArticleDetailView,
    ArticleListCreateView,
    ArticlePipelineFlowView,
    ArticlePublishView,
    ArticleVersionListView,
    ArticleVersionRestoreView,
    MediaAssetListCreateView,
    PublicArticleDetailView,
    PublicArticleListView,
    PublicArticlePipelineFlowView,
)

app_name = "content"

urlpatterns = [
    # Management routes (authenticated workspace members)
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/articles/",
        ArticleListCreateView.as_view(),
        name="article_list_create",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/articles/<uuid:article_id>/",
        ArticleDetailView.as_view(),
        name="article_detail",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/articles/<uuid:article_id>/publish/",
        ArticlePublishView.as_view(),
        name="article_publish",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/articles/<uuid:article_id>/pipeline-flow/",
        ArticlePipelineFlowView.as_view(),
        name="article_pipeline_flow",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/articles/<uuid:article_id>/versions/",
        ArticleVersionListView.as_view(),
        name="article_version_list",
    ),
    path(
        "workspaces/<uuid:workspace_id>/sites/<uuid:site_id>/articles/<uuid:article_id>/versions/<int:version_number>/restore/",
        ArticleVersionRestoreView.as_view(),
        name="article_version_restore",
    ),
    path(
        "workspaces/<uuid:workspace_id>/media/",
        MediaAssetListCreateView.as_view(),
        name="media_asset_list_create",
    ),
    # Public headless content delivery routes (unauthenticated)
    path(
        "public/sites/<slug:site_slug>/articles/",
        PublicArticleListView.as_view(),
        name="public_article_list",
    ),
    path(
        "public/sites/<slug:site_slug>/articles/<slug:article_slug>/",
        PublicArticleDetailView.as_view(),
        name="public_article_detail",
    ),
    path(
        "public/sites/<slug:site_slug>/articles/<slug:article_slug>/pipeline-flow/",
        PublicArticlePipelineFlowView.as_view(),
        name="public_article_pipeline_flow",
    ),
]
