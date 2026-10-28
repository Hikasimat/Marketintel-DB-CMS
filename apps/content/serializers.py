"""Serializers for Article content, revisions, and media assets."""

from __future__ import annotations

from typing import Any, ClassVar

from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.content.models import Article, ArticleVersion, MediaAsset


class ArticleVersionSerializer(serializers.ModelSerializer[ArticleVersion]):
    created_by = UserSerializer(read_only=True)

    class Meta:
        model = ArticleVersion
        fields = (
            "id",
            "version_number",
            "title",
            "excerpt",
            "body",
            "metadata",
            "created_by",
            "created_at",
        )
        read_only_fields = fields


class ArticleSerializer(serializers.ModelSerializer[Article]):
    author = UserSerializer(read_only=True)
    versions_count = serializers.SerializerMethodField()

    class Meta:
        model = Article
        fields = (
            "id",
            "title",
            "slug",
            "excerpt",
            "body",
            "content_type",
            "status",
            "published_at",
            "metadata",
            "author",
            "versions_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "author", "versions_count", "created_at", "updated_at")

    def get_versions_count(self, obj: Article) -> int:
        return obj.versions.count()


class ArticleCreateUpdateSerializer(serializers.ModelSerializer[Article]):
    class Meta:
        model = Article
        fields = (
            "title",
            "slug",
            "excerpt",
            "body",
            "content_type",
            "status",
            "metadata",
        )
        extra_kwargs: ClassVar[dict[str, Any]] = {"slug": {"required": False}}


class PublicArticleSerializer(serializers.ModelSerializer[Article]):
    """Clean, public-facing representation of published articles."""

    class Meta:
        model = Article
        fields = (
            "id",
            "title",
            "slug",
            "excerpt",
            "body",
            "content_type",
            "published_at",
            "metadata",
        )
        read_only_fields = fields


class MediaAssetSerializer(serializers.ModelSerializer[MediaAsset]):
    uploaded_by = UserSerializer(read_only=True)

    class Meta:
        model = MediaAsset
        fields = (
            "id",
            "filename",
            "content_type",
            "file_size",
            "storage_path",
            "checksum_sha256",
            "uploaded_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class MediaAssetCreateSerializer(serializers.Serializer[Any]):
    filename = serializers.CharField(max_length=255)
    content_type = serializers.CharField(max_length=100)
    file_size = serializers.IntegerField(min_value=1, max_value=10_485_760)  # max 10MB bound
    storage_path = serializers.CharField(max_length=500)
    checksum_sha256 = serializers.CharField(max_length=64, required=False, default="")
