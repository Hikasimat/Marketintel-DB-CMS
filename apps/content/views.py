"""Views for Article content management, revisions, media, and public content delivery."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from django.db import transaction
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.audit.services import record_audit_event
from apps.common.pagination import DefaultPagination
from apps.content.models import Article, ArticleStatus, ArticleVersion, MediaAsset
from apps.content.serializers import (
    ArticleCreateUpdateSerializer,
    ArticleSerializer,
    ArticleVersionSerializer,
    MediaAssetCreateSerializer,
    MediaAssetSerializer,
    PublicArticleSerializer,
)
from apps.content.services import (
    create_article_version,
    publish_article,
    restore_article_version,
)
from apps.sites.models import Site
from apps.sites.views import _get_site
from apps.tenancy.permissions import (
    IsWorkspaceAdmin,
    IsWorkspaceEditor,
    IsWorkspaceMember,
    resolve_workspace,
)


def _get_article(site: Site, article_id: Any) -> Article:
    if isinstance(article_id, uuid.UUID):
        a_id = article_id
    else:
        try:
            a_id = uuid.UUID(str(article_id))
        except ValueError as exc:
            raise NotFound("Article not found.") from exc

    article = Article.objects.filter(site=site, id=a_id).first()
    if article is None:
        raise NotFound("Article not found for this site.")
    return article


def _check_public_origin_allowlist(request: Request, site: Site) -> None:
    """Validate request Origin header against Site allowed_origins (CT-6)."""
    origin = request.headers.get("Origin")
    if not origin:
        # Server-side / SSR requests without Origin header are permitted
        return

    allowed = site.allowed_origins or []
    if "*" in allowed:
        return

    normalized_origin = origin.strip().rstrip("/")
    normalized_allowed = [o.strip().rstrip("/") for o in allowed]

    if normalized_origin not in normalized_allowed:
        raise PermissionDenied(
            f"Origin '{origin}' is not authorized to access content for this site."
        )


class ArticleListCreateView(APIView):
    """List or create articles in a site."""

    pagination_class = DefaultPagination

    def get_permissions(self) -> list[permissions.BasePermission]:
        if self.request.method == "POST":
            return [permissions.IsAuthenticated(), IsWorkspaceEditor()]
        return [permissions.IsAuthenticated(), IsWorkspaceMember()]

    @extend_schema(responses={200: ArticleSerializer(many=True)})
    def get(
        self, request: Request, workspace_id: str, site_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)

        articles = (
            Article.objects.filter(site=site).select_related("author").order_by("-created_at")
        )

        status_param = request.query_params.get("status")
        if status_param:
            articles = articles.filter(status=status_param.upper())

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(articles, request, view=self)
        if page is not None:
            serializer = ArticleSerializer(page, many=True)
            return paginator.get_paginated_response(list(serializer.data))

        serializer = ArticleSerializer(articles, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        request=ArticleCreateUpdateSerializer,
        responses={201: ArticleSerializer, 400: OpenApiResponse(description="Validation error")},
    )
    def post(
        self, request: Request, workspace_id: str, site_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)

        user = request.user
        author = user if isinstance(user, User) else None

        serializer = ArticleCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        slug = serializer.validated_data.get("slug")
        if slug and Article.objects.filter(site=site, slug=slug).exists():
            raise ValidationError(
                {"slug": ["An article with this slug already exists on this site."]}
            )

        with transaction.atomic():
            article = serializer.save(site=site, author=author)
            # Create version 1 revision snapshot
            create_article_version(article, user=author)

            record_audit_event(
                action="article.created",
                request=request,
                workspace_id=workspace.id,
                resource_type="article",
                resource_id=str(article.id),
                payload={"title": article.title, "slug": article.slug},
            )

        return Response(ArticleSerializer(article).data, status=status.HTTP_201_CREATED)


class ArticleDetailView(APIView):
    """Retrieve, update, or delete an article."""

    def get_permissions(self) -> list[permissions.BasePermission]:
        if self.request.method == "DELETE":
            return [permissions.IsAuthenticated(), IsWorkspaceAdmin()]
        if self.request.method in ("PATCH", "PUT"):
            return [permissions.IsAuthenticated(), IsWorkspaceEditor()]
        return [permissions.IsAuthenticated(), IsWorkspaceMember()]

    @extend_schema(
        responses={200: ArticleSerializer, 404: OpenApiResponse(description="Article not found")}
    )
    def get(
        self,
        request: Request,
        workspace_id: str,
        site_id: str,
        article_id: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)
        article = _get_article(site, article_id)
        return Response(ArticleSerializer(article).data, status=status.HTTP_200_OK)

    @extend_schema(request=ArticleCreateUpdateSerializer, responses={200: ArticleSerializer})
    def patch(
        self,
        request: Request,
        workspace_id: str,
        site_id: str,
        article_id: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)
        article = _get_article(site, article_id)

        serializer = ArticleCreateUpdateSerializer(article, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        user = request.user
        editor = user if isinstance(user, User) else None

        with transaction.atomic():
            updated_article = serializer.save()
            create_article_version(updated_article, user=editor)

            record_audit_event(
                action="article.updated",
                request=request,
                workspace_id=workspace.id,
                resource_type="article",
                resource_id=str(article.id),
                payload={"changes": request.data},
            )

        return Response(ArticleSerializer(updated_article).data, status=status.HTTP_200_OK)

    @extend_schema(responses={204: OpenApiResponse(description="Article deleted")})
    def delete(
        self,
        request: Request,
        workspace_id: str,
        site_id: str,
        article_id: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)
        article = _get_article(site, article_id)

        title = article.title
        a_id = str(article.id)
        article.delete()

        record_audit_event(
            action="article.deleted",
            request=request,
            workspace_id=workspace.id,
            resource_type="article",
            resource_id=a_id,
            payload={"title": title},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ArticlePublishView(APIView):
    """Publish an article and capture publication snapshot."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceEditor)

    @extend_schema(request=None, responses={200: ArticleSerializer})
    def post(
        self,
        request: Request,
        workspace_id: str,
        site_id: str,
        article_id: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)
        article = _get_article(site, article_id)

        user = request.user
        if not isinstance(user, User):
            raise PermissionDenied("Authentication required.")

        published_art = publish_article(article, user=user, request=request)
        return Response(ArticleSerializer(published_art).data, status=status.HTTP_200_OK)


class ArticleVersionListView(APIView):
    """List revision version history for an article."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceMember)

    @extend_schema(responses={200: ArticleVersionSerializer(many=True)})
    def get(
        self,
        request: Request,
        workspace_id: str,
        site_id: str,
        article_id: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)
        article = _get_article(site, article_id)

        versions = (
            ArticleVersion.objects.filter(article=article)
            .select_related("created_by")
            .order_by("-version_number")
        )
        return Response(
            ArticleVersionSerializer(versions, many=True).data, status=status.HTTP_200_OK
        )


class ArticleVersionRestoreView(APIView):
    """Restore an article's content from a prior revision version."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceEditor)

    @extend_schema(
        request=None,
        responses={200: ArticleSerializer, 404: OpenApiResponse(description="Version not found")},
    )
    def post(
        self,
        request: Request,
        workspace_id: str,
        site_id: str,
        article_id: str,
        version_number: int,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)
        article = _get_article(site, article_id)

        user = request.user
        if not isinstance(user, User):
            raise PermissionDenied("Authentication required.")

        if not ArticleVersion.objects.filter(
            article=article, version_number=version_number
        ).exists():
            raise NotFound(f"Version {version_number} not found for this article.")

        restored_art = restore_article_version(
            article, version_number=version_number, user=user, request=request
        )
        return Response(ArticleSerializer(restored_art).data, status=status.HTTP_200_OK)


class MediaAssetListCreateView(APIView):
    """List or catalog media assets in a workspace."""

    pagination_class = DefaultPagination

    def get_permissions(self) -> list[permissions.BasePermission]:
        if self.request.method == "POST":
            return [permissions.IsAuthenticated(), IsWorkspaceEditor()]
        return [permissions.IsAuthenticated(), IsWorkspaceMember()]

    @extend_schema(responses={200: MediaAssetSerializer(many=True)})
    def get(self, request: Request, workspace_id: str, *args: Any, **kwargs: Any) -> Response:
        workspace = resolve_workspace(request, self)
        assets = (
            MediaAsset.objects.filter(workspace=workspace)
            .select_related("uploaded_by")
            .order_by("-created_at")
        )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(assets, request, view=self)
        if page is not None:
            serializer = MediaAssetSerializer(page, many=True)
            return paginator.get_paginated_response(list(serializer.data))

        return Response(MediaAssetSerializer(assets, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        request=MediaAssetCreateSerializer,
        responses={201: MediaAssetSerializer, 400: OpenApiResponse(description="Validation error")},
    )
    def post(self, request: Request, workspace_id: str, *args: Any, **kwargs: Any) -> Response:
        workspace = resolve_workspace(request, self)
        user = request.user
        uploader = user if isinstance(user, User) else None

        serializer = MediaAssetCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        asset = MediaAsset.objects.create(
            workspace=workspace,
            filename=serializer.validated_data["filename"],
            content_type=serializer.validated_data["content_type"],
            file_size=serializer.validated_data["file_size"],
            storage_path=serializer.validated_data["storage_path"],
            checksum_sha256=serializer.validated_data.get("checksum_sha256", ""),
            uploaded_by=uploader,
        )

        record_audit_event(
            action="media.uploaded",
            request=request,
            workspace_id=workspace.id,
            resource_type="media",
            resource_id=str(asset.id),
            payload={"filename": asset.filename, "file_size": asset.file_size},
        )

        return Response(MediaAssetSerializer(asset).data, status=status.HTTP_201_CREATED)


class PublicArticleListView(APIView):
    """Public read-only content delivery endpoint for published articles (CT-4, CT-6)."""

    permission_classes = (permissions.AllowAny,)
    authentication_classes = ()
    pagination_class = DefaultPagination

    @extend_schema(
        responses={
            200: PublicArticleSerializer(many=True),
            404: OpenApiResponse(description="Site not found"),
        }
    )
    def get(self, request: Request, site_slug: str, *args: Any, **kwargs: Any) -> Response:
        site = Site.objects.filter(slug=site_slug, is_active=True).first()
        if site is None:
            raise NotFound("Site not found or inactive.")

        _check_public_origin_allowlist(request, site)

        articles = Article.objects.filter(site=site, status=ArticleStatus.PUBLISHED).order_by(
            "-published_at"
        )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(articles, request, view=self)
        if page is not None:
            serializer = PublicArticleSerializer(page, many=True)
            response = paginator.get_paginated_response(list(serializer.data))
        else:
            serializer = PublicArticleSerializer(articles, many=True)
            response = Response(serializer.data, status=status.HTTP_200_OK)

        # Attach cache headers
        response["Cache-Control"] = "public, max-age=60"
        return response


class PublicArticleDetailView(APIView):
    """Public read-only content delivery endpoint for a single published article (CT-4, CT-6)."""

    permission_classes = (permissions.AllowAny,)
    authentication_classes = ()

    @extend_schema(
        responses={
            200: PublicArticleSerializer,
            404: OpenApiResponse(description="Article not found"),
        },
    )
    def get(
        self, request: Request, site_slug: str, article_slug: str, *args: Any, **kwargs: Any
    ) -> Response:
        site = Site.objects.filter(slug=site_slug, is_active=True).first()
        if site is None:
            raise NotFound("Site not found or inactive.")

        _check_public_origin_allowlist(request, site)

        article = Article.objects.filter(
            site=site, slug=article_slug, status=ArticleStatus.PUBLISHED
        ).first()

        if article is None:
            raise NotFound("Article not found.")

        serializer = PublicArticleSerializer(article)
        response = Response(serializer.data, status=status.HTTP_200_OK)

        # Generate ETag based on updated_at and id
        etag = hashlib.sha256(f"{article.id}:{article.updated_at}".encode()).hexdigest()
        response["ETag"] = f'"{etag}"'
        response["Cache-Control"] = "public, max-age=60"
        return response


def build_article_pipeline_flow(
    site: Site, article: Article, redact_sensitive: bool = False
) -> dict:
    """Evaluate and compile the 7-step publishing pipeline diagnostics for an article."""
    # Step 1: Content & Slug Validation
    slug_valid = bool(article.slug and not any(c in article.slug for c in " /\\?#@!"))
    word_count = len(article.body.split()) if article.body else 0
    step1_status = "PASSED" if (slug_valid and article.title) else "FAILED"
    step1_details = (
        f"Slug '{article.slug}' is valid. Title length: {len(article.title)} characters. "
        f"Body word count: {word_count} words."
    )
    step1_error = None if slug_valid else "Slug contains invalid characters."

    # Step 2: Version Snapshots & Revision History
    versions = list(ArticleVersion.objects.filter(article=article).order_by("-version_number"))
    latest_ver = versions[0] if versions else None
    author_email = (
        latest_ver.created_by.email if (latest_ver and latest_ver.created_by) else "admin@cms.local"
    )
    if redact_sensitive and "@" in author_email:
        name_part, domain_part = author_email.split("@", 1)
        author_email = f"{name_part[:2]}***@{domain_part}"

    step2_status = "PASSED" if versions else "WARNING"
    active_v = latest_ver.version_number if latest_ver else 1
    step2_details = (
        f"Total revisions: {len(versions)}. Active snapshot version: #{active_v} "
        f"(authored by {author_email})."
    )

    # Step 3: Domain & Canonical Resolution
    primary_domain = (
        site.domains.filter(is_verified=True, is_primary=True).first()
        or site.domains.filter(is_verified=True).first()
    )
    if primary_domain:
        domain_url = f"https://{primary_domain.hostname}"
        step3_status = "PASSED"
        step3_details = f"Verified domain active: {domain_url}"
    else:
        domain_url = f"https://{site.slug}.cms.local"
        step3_status = "WARNING"
        step3_details = (
            f"No verified custom domain registered; using local delivery fallback: {domain_url}"
        )

    # Step 4: Public Delivery Availability
    is_published = article.status == ArticleStatus.PUBLISHED
    if is_published:
        step4_status = "PASSED"
        step4_details = (
            f"Live snapshot actively delivered at "
            f"/api/v1/public/sites/{site.slug}/articles/{article.slug}/"
        )
        step4_error = None
    elif article.status == ArticleStatus.DRAFT:
        step4_status = "PENDING"
        step4_details = (
            "Article is currently in DRAFT state. "
            "Not accessible via public delivery until published."
        )
        step4_error = "Article is not published yet."
    else:
        step4_status = "WARNING"
        step4_details = f"Article status is {article.status}. Public delivery is inactive."
        step4_error = f"Status is {article.status}."

    # Step 5: Dynamic XML Sitemap Inclusion
    seo_meta = getattr(article, "seo", None)
    robots_index = seo_meta.robots_index if seo_meta else True
    if is_published and robots_index:
        step5_status = "PASSED"
        step5_details = (
            f"Included in dynamic sitemap at /api/v1/public/sites/{site.slug}/sitemap.xml"
        )
        step5_error = None
    elif not robots_index:
        step5_status = "SKIPPED"
        step5_details = "Excluded from sitemap because robots_index is set to False (noindex)."
        step5_error = None
    else:
        step5_status = "SKIPPED"
        step5_details = "Draft articles are excluded from dynamic XML sitemap."
        step5_error = None

    # Step 6: Search Engine Indexing Submissions
    try:
        from apps.integrations.models import IndexSubmissionLog

        submission_logs = list(
            IndexSubmissionLog.objects.filter(site=site).order_by("-created_at")[:20]
        )
        matching_logs = [
            sub_log
            for sub_log in submission_logs
            if any(article.slug in u for u in (sub_log.urls or []))
        ]
    except Exception:
        matching_logs = []

    if matching_logs:
        has_failed = any(sub_log.status == "FAILED" for sub_log in matching_logs)
        has_pending = any(sub_log.status == "PENDING" for sub_log in matching_logs)
        if has_failed:
            step6_status = "FAILED"
            failed_log = next(sub_log for sub_log in matching_logs if sub_log.status == "FAILED")
            err_msg = failed_log.response_body or "Unknown error"
            step6_details = f"Submission error on provider {failed_log.provider}: {err_msg}"
            step6_error = failed_log.response_body
        elif has_pending:
            step6_status = "PENDING"
            step6_details = f"{len(matching_logs)} submission(s) queued in Celery worker."
            step6_error = None
        else:
            step6_status = "PASSED"
            providers_str = ", ".join(sorted({sub_log.provider for sub_log in matching_logs}))
            step6_details = f"Successfully notified search engines ({providers_str})."
            step6_error = None

        logs_summary = [
            {
                "id": str(sub_log.id),
                "provider": sub_log.provider,
                "status": sub_log.status,
                "urls": sub_log.urls,
                "response_code": sub_log.response_code,
                "response_body": sub_log.response_body,
                "created_at": sub_log.created_at.isoformat(),
            }
            for sub_log in matching_logs
        ]
    else:
        step6_status = "INFO"
        step6_details = (
            "No automated or manual search engine indexing submissions logged for this article yet."
        )
        step6_error = None
        logs_summary = []

    # Step 7: Security Audit Trail
    try:
        from apps.audit.models import AuditEvent

        audit_records = list(
            AuditEvent.objects.filter(
                resource_type="article", resource_id=str(article.id)
            ).order_by("-timestamp")[:5]
        )
        step7_status = "PASSED" if audit_records else "INFO"
        step7_details = f"{len(audit_records)} audit event(s) recorded for this article."
        audit_summary = []
        for a in audit_records:
            actor_name = a.actor_email or str(a.actor_id)
            if redact_sensitive and "@" in actor_name:
                np, dp = actor_name.split("@", 1)
                actor_name = f"{np[:2]}***@{dp}"
            audit_summary.append(
                {
                    "action": a.action,
                    "actor": actor_name,
                    "timestamp": a.timestamp.isoformat(),
                }
            )
    except Exception:
        step7_status = "INFO"
        step7_details = "No audit events logged yet."
        audit_summary = []

    overall = (
        "SUCCESS"
        if (step1_status == "PASSED" and step4_status == "PASSED" and step6_status != "FAILED")
        else (
            "WARNING"
            if (step4_status == "PENDING" or step6_status == "PENDING" or step3_status == "WARNING")
            else "FAILED"
        )
    )

    return {
        "article": {
            "id": str(article.id),
            "title": article.title,
            "slug": article.slug,
            "status": article.status,
            "published_at": (article.published_at.isoformat() if article.published_at else None),
            "site_slug": site.slug,
            "site_name": site.name,
        },
        "overall_status": overall,
        "steps": [
            {
                "step_id": "content_validation",
                "title": "1. Content Integrity & Slug Validation",
                "status": step1_status,
                "details": step1_details,
                "error": step1_error,
            },
            {
                "step_id": "versioning",
                "title": "2. Version Snapshot & Revision History",
                "status": step2_status,
                "details": step2_details,
                "error": None,
            },
            {
                "step_id": "domain_resolution",
                "title": "3. Site Domain & Base URL Resolution",
                "status": step3_status,
                "details": step3_details,
                "error": None,
            },
            {
                "step_id": "public_delivery",
                "title": "4. Public Delivery API Availability",
                "status": step4_status,
                "details": step4_details,
                "error": step4_error,
            },
            {
                "step_id": "sitemap_inclusion",
                "title": "5. Dynamic XML Sitemap Verification",
                "status": step5_status,
                "details": step5_details,
                "error": step5_error,
            },
            {
                "step_id": "indexing_dispatch",
                "title": "6. Search Engine Indexing Submissions (Google & IndexNow)",
                "status": step6_status,
                "details": step6_details,
                "error": step6_error,
                "logs": logs_summary,
            },
            {
                "step_id": "audit_trail",
                "title": "7. Security Audit Trail",
                "status": step7_status,
                "details": step7_details,
                "events": audit_summary,
            },
        ],
    }


class ArticlePipelineFlowView(APIView):
    """Inspect the end-to-end publishing pipeline flow and health for an article (management)."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceMember)

    @extend_schema(
        responses={200: OpenApiResponse(description="Publishing pipeline flow details")},
    )
    def get(
        self,
        request: Request,
        workspace_id: str,
        site_id: str,
        article_id: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)
        article = _get_article(site, article_id)
        data = build_article_pipeline_flow(site, article, redact_sensitive=False)
        return Response(data, status=status.HTTP_200_OK)


class PublicArticlePipelineFlowView(APIView):
    """Public read-only pipeline flow inspection for QA and monitoring."""

    permission_classes = (permissions.AllowAny,)
    authentication_classes = ()

    @extend_schema(
        responses={
            200: OpenApiResponse(description="Public article publishing pipeline flow details")
        },
    )
    def get(
        self,
        request: Request,
        site_slug: str,
        article_slug: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        site = Site.objects.filter(slug=site_slug, is_active=True).first()
        if site is None:
            raise NotFound("Site not found or inactive.")

        _check_public_origin_allowlist(request, site)

        article = Article.objects.filter(site=site, slug=article_slug).first()
        if article is None:
            raise NotFound("Article not found.")

        data = build_article_pipeline_flow(site, article, redact_sensitive=True)
        return Response(data, status=status.HTTP_200_OK)
