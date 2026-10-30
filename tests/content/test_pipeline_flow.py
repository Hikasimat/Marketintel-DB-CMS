"""Tests for Article publishing pipeline flow diagnostics endpoint."""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.content.models import Article, ArticleStatus
from apps.integrations.models import IndexSubmissionLog
from apps.sites.models import Site
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole

pytestmark = pytest.mark.django_db


def test_article_pipeline_flow_authenticated():
    client = APIClient()
    user = User.objects.create_user(email="editor@test.com", password="Password123!")
    workspace = Workspace.objects.create(name="Flow Test WS", slug="flow-test-ws")
    WorkspaceMembership.objects.create(workspace=workspace, user=user, role=WorkspaceRole.ADMIN)
    site = Site.objects.create(workspace=workspace, name="TechFlow", slug="techflow")

    client.force_authenticate(user=user)

    # 1. Create a draft article
    create_url = reverse(
        "content:article_list_create",
        kwargs={"workspace_id": workspace.id, "site_id": site.id},
    )
    art_resp = client.post(
        create_url,
        {
            "title": "Pipeline Inspection Article",
            "slug": "pipeline-inspect-slug",
            "body": "Detailed content testing 7-step pipeline diagnostics.",
            "status": "DRAFT",
        },
        format="json",
    )
    assert art_resp.status_code == status.HTTP_201_CREATED
    art_id = art_resp.json()["id"]

    # 2. Query pipeline-flow for DRAFT
    flow_url = reverse(
        "content:article_pipeline_flow",
        kwargs={"workspace_id": workspace.id, "site_id": site.id, "article_id": art_id},
    )
    flow_resp = client.get(flow_url)
    assert flow_resp.status_code == status.HTTP_200_OK
    flow_data = flow_resp.json()

    assert flow_data["article"]["slug"] == "pipeline-inspect-slug"
    assert flow_data["article"]["status"] == ArticleStatus.DRAFT
    steps = {s["step_id"]: s for s in flow_data["steps"]}
    assert len(steps) == 7
    assert steps["content_validation"]["status"] == "PASSED"
    assert steps["public_delivery"]["status"] == "PENDING"
    assert "not accessible via public delivery" in steps["public_delivery"]["details"].lower()

    # 3. Publish the article
    pub_url = reverse(
        "content:article_publish",
        kwargs={"workspace_id": workspace.id, "site_id": site.id, "article_id": art_id},
    )
    pub_resp = client.post(pub_url)
    assert pub_resp.status_code == status.HTTP_200_OK

    # Simulate an indexing submission log
    site_obj = Site.objects.get(id=site.id)
    IndexSubmissionLog.objects.create(
        site=site_obj,
        provider="GOOGLE",
        status="SUBMITTED",
        urls=["https://techflow.cms.local/articles/pipeline-inspect-slug"],
        response_code=200,
        response_body="OK",
    )

    # 4. Check pipeline-flow after publishing
    flow_resp2 = client.get(flow_url)
    assert flow_resp2.status_code == status.HTTP_200_OK
    flow_data2 = flow_resp2.json()

    assert flow_data2["article"]["status"] == ArticleStatus.PUBLISHED
    steps2 = {s["step_id"]: s for s in flow_data2["steps"]}
    assert steps2["public_delivery"]["status"] == "PASSED"
    assert steps2["sitemap_inclusion"]["status"] == "PASSED"
    assert steps2["indexing_dispatch"]["status"] == "PASSED"
    assert len(steps2["indexing_dispatch"]["logs"]) >= 1
    assert steps2["indexing_dispatch"]["logs"][0]["provider"] == "GOOGLE"


def test_public_article_pipeline_flow():
    client = APIClient()
    workspace = Workspace.objects.create(name="Pub Flow WS", slug="pub-flow-ws")
    site = Site.objects.create(workspace=workspace, name="PublicSite", slug="public-site")
    article = Article.objects.create(
        site=site,
        title="Public Article Pipeline",
        slug="public-article-pipeline",
        body="Public body text.",
        status=ArticleStatus.PUBLISHED,
    )

    public_flow_url = reverse(
        "content:public_article_pipeline_flow",
        kwargs={"site_slug": site.slug, "article_slug": article.slug},
    )

    # Unauthenticated client request
    res = client.get(public_flow_url)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["article"]["slug"] == "public-article-pipeline"
    assert data["overall_status"] in ("SUCCESS", "WARNING")
    steps = {s["step_id"]: s for s in data["steps"]}
    assert steps["content_validation"]["status"] == "PASSED"
    assert steps["public_delivery"]["status"] == "PASSED"
