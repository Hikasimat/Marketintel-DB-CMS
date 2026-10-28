"""Tests for Article content lifecycle, publishing workflow, revisions, and media assets."""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.content.models import ArticleStatus, ArticleVersion
from apps.sites.models import Site
from apps.tenancy.models import Workspace, WorkspaceMembership, WorkspaceRole

pytestmark = pytest.mark.django_db


def test_article_lifecycle_and_versioning():
    client = APIClient()
    editor = User.objects.create_user(email="writer@org.com", password="SecurePassword123!")
    workspace = Workspace.objects.create(name="Editorial WS", slug="editorial-ws")
    WorkspaceMembership.objects.create(workspace=workspace, user=editor, role=WorkspaceRole.EDITOR)

    site = Site.objects.create(workspace=workspace, name="Magazine", slug="magazine")

    client.force_authenticate(user=editor)
    articles_url = reverse(
        "content:article_list_create",
        kwargs={"workspace_id": workspace.id, "site_id": site.id},
    )

    # 1. Create Article (version 1 created automatically)
    create_resp = client.post(
        articles_url,
        {
            "title": "Breaking Tech News",
            "slug": "breaking-tech-news",
            "excerpt": "Short excerpt here.",
            "body": "# First Draft Content\nDetailed article body.",
            "content_type": "POST",
        },
        format="json",
    )
    assert create_resp.status_code == status.HTTP_201_CREATED
    art_data = create_resp.json()
    article_id = art_data["id"]
    assert art_data["status"] == ArticleStatus.DRAFT
    assert art_data["versions_count"] == 1

    # Verify version 1 in DB
    versions = ArticleVersion.objects.filter(article_id=article_id)
    assert versions.count() == 1
    assert versions.first().version_number == 1
    assert versions.first().title == "Breaking Tech News"

    # 2. Update Article (captures version 2)
    art_url = reverse(
        "content:article_detail",
        kwargs={"workspace_id": workspace.id, "site_id": site.id, "article_id": article_id},
    )
    patch_resp = client.patch(
        art_url,
        {"body": "# Second Draft Content\nExpanded details and edits."},
        format="json",
    )
    assert patch_resp.status_code == status.HTTP_200_OK
    assert patch_resp.json()["versions_count"] == 2

    # 3. Publish Article
    publish_url = reverse(
        "content:article_publish",
        kwargs={"workspace_id": workspace.id, "site_id": site.id, "article_id": article_id},
    )
    pub_resp = client.post(publish_url)
    assert pub_resp.status_code == status.HTTP_200_OK
    pub_data = pub_resp.json()
    assert pub_data["status"] == ArticleStatus.PUBLISHED
    assert pub_data["published_at"] is not None
    assert pub_data["versions_count"] == 3

    # 4. Rollback / Restore Version 1
    restore_url = reverse(
        "content:article_version_restore",
        kwargs={
            "workspace_id": workspace.id,
            "site_id": site.id,
            "article_id": article_id,
            "version_number": 1,
        },
    )
    restore_resp = client.post(restore_url)
    assert restore_resp.status_code == status.HTTP_200_OK
    restored_data = restore_resp.json()
    # Body was restored to version 1's content
    assert restored_data["body"] == "# First Draft Content\nDetailed article body."
    # A new version (version 4) was recorded documenting the restore
    assert restored_data["versions_count"] == 4


def test_media_asset_catalog():
    client = APIClient()
    editor = User.objects.create_user(email="designer@org.com", password="SecurePassword123!")
    workspace = Workspace.objects.create(name="Creative WS", slug="creative-ws")
    WorkspaceMembership.objects.create(workspace=workspace, user=editor, role=WorkspaceRole.EDITOR)

    client.force_authenticate(user=editor)
    media_url = reverse("content:media_asset_list_create", kwargs={"workspace_id": workspace.id})

    # Catalog valid asset
    create_resp = client.post(
        media_url,
        {
            "filename": "hero-image.png",
            "content_type": "image/png",
            "file_size": 204800,
            "storage_path": "uploads/creative-ws/hero-image.png",
            "checksum_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        },
        format="json",
    )
    assert create_resp.status_code == status.HTTP_201_CREATED
    asset_data = create_resp.json()
    assert asset_data["filename"] == "hero-image.png"

    # Reject oversized file (> 10MB bound)
    oversized_resp = client.post(
        media_url,
        {
            "filename": "huge-video.mp4",
            "content_type": "video/mp4",
            "file_size": 50_000_000,
            "storage_path": "uploads/creative-ws/huge-video.mp4",
        },
        format="json",
    )
    assert oversized_resp.status_code == status.HTTP_400_BAD_REQUEST
