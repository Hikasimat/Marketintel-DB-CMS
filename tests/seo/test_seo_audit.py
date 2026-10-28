"""Tests for SEO automated diagnostics audit endpoint (SEO-7)."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.content.models import Article, ArticleStatus
from apps.seo.models import ArticleSEO
from apps.sites.models import Site
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole


@pytest.fixture
def audit_setup(db: None) -> dict[str, object]:
    member = User.objects.create_user(email="member@audit.com", password="SecurePassword123!")
    workspace = Workspace.objects.create(name="Audit WS", slug="audit-ws")
    WorkspaceMembership.objects.create(workspace=workspace, user=member, role=WorkspaceRole.EDITOR)

    site = Site.objects.create(workspace=workspace, name="Audit Site", slug="audit-site")

    # 1. Article with excessively long title (>60 chars) and missing description
    art1 = Article.objects.create(
        site=site,
        author=member,
        title=(
            "This is an excessively long title designed specifically to exceed sixty characters "
            "in length for testing"
        ),
        slug="long-title-post",
        excerpt="",
        body="Body content",
        status=ArticleStatus.PUBLISHED,
    )

    # 2. Article with excessively long description (>160 chars) and noindex
    art2 = Article.objects.create(
        site=site,
        author=member,
        title="Valid Title",
        slug="valid-title-post",
        excerpt="A" * 200,  # 200 characters long
        body="Body content",
        status=ArticleStatus.PUBLISHED,
    )
    ArticleSEO.objects.create(article=art2, robots_index=False)

    return {
        "member": member,
        "workspace": workspace,
        "site": site,
        "art1": art1,
        "art2": art2,
    }


@pytest.mark.django_db
def test_seo_audit_diagnostics(audit_setup: dict[str, object]) -> None:
    client = APIClient()
    member = audit_setup["member"]
    workspace = audit_setup["workspace"]
    site = audit_setup["site"]
    assert isinstance(workspace, Workspace)
    assert isinstance(site, Site)

    url = reverse("seo:seo_audit", kwargs={"workspace_id": workspace.id, "site_id": site.id})

    client.force_authenticate(user=member)
    resp = client.get(url)
    assert resp.status_code == status.HTTP_200_OK

    diagnostics = resp.json()
    codes = [d["code"] for d in diagnostics]

    # Verify expected diagnostic codes are reported
    assert "TITLE_TOO_LONG" in codes
    assert "DESCRIPTION_MISSING" in codes
    assert "DESCRIPTION_TOO_LONG" in codes
    assert "PUBLISHED_NOINDEX" in codes
    assert "OG_IMAGE_MISSING" in codes

    # Each diagnostic has required fields
    for diag in diagnostics:
        assert "article_id" in diag
        assert "field" in diag
        assert "severity" in diag
        assert "message" in diag
        assert "remediation" in diag
