"""Views for Site and Article SEO management, redirects, audits, and public SEO feeds."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from django.http import HttpResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit_event
from apps.common.pagination import DefaultPagination
from apps.content.models import Article, ArticleStatus
from apps.content.views import _check_public_origin_allowlist, _get_article
from apps.seo.models import ArticleSEO, RedirectRule, SiteSEOSettings
from apps.seo.serializers import (
    ArticleSEOSerializer,
    PublicSEOMetadataSerializer,
    RedirectRuleSerializer,
    SEOAuditItemSerializer,
    SiteSEOSettingsSerializer,
)
from apps.seo.services import (
    generate_robots_txt,
    generate_sitemap_xml,
    resolve_article_seo,
    run_seo_audit,
)
from apps.sites.models import Site
from apps.sites.views import _get_site
from apps.tenancy.permissions import (
    IsWorkspaceAdmin,
    IsWorkspaceEditor,
    IsWorkspaceMember,
    resolve_workspace,
)


def _get_redirect_rule(site: Site, rule_id: Any) -> RedirectRule:
    if isinstance(rule_id, uuid.UUID):
        r_id = rule_id
    else:
        try:
            r_id = uuid.UUID(str(rule_id))
        except ValueError as exc:
            raise NotFound("Redirect rule not found.") from exc

    rule = RedirectRule.objects.filter(site=site, id=r_id).first()
    if rule is None:
        raise NotFound("Redirect rule not found.")
    return rule


class SiteSEOSettingsView(APIView):
    """Retrieve or update site-wide SEO defaults (SEO-1, SEO-6)."""

    def get_permissions(self) -> list[permissions.BasePermission]:
        if self.request.method in ("PATCH", "PUT"):
            return [permissions.IsAuthenticated(), IsWorkspaceAdmin()]
        return [permissions.IsAuthenticated(), IsWorkspaceMember()]

    @extend_schema(responses={200: SiteSEOSettingsSerializer})
    def get(
        self, request: Request, workspace_id: str, site_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)
        settings, _ = SiteSEOSettings.objects.get_or_create(site=site)
        return Response(SiteSEOSettingsSerializer(settings).data, status=status.HTTP_200_OK)

    @extend_schema(request=SiteSEOSettingsSerializer, responses={200: SiteSEOSettingsSerializer})
    def patch(
        self, request: Request, workspace_id: str, site_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)
        settings, _ = SiteSEOSettings.objects.get_or_create(site=site)

        serializer = SiteSEOSettingsSerializer(settings, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        record_audit_event(
            action="seo.site_settings_updated",
            request=request,
            workspace_id=workspace.id,
            resource_type="seo_settings",
            resource_id=str(settings.id),
            payload={"title_suffix": settings.title_suffix},
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class ArticleSEOView(APIView):
    """Retrieve or update article-specific SEO metadata (SEO-1, SEO-2, SEO-3)."""

    def get_permissions(self) -> list[permissions.BasePermission]:
        if self.request.method in ("PATCH", "PUT"):
            return [permissions.IsAuthenticated(), IsWorkspaceEditor()]
        return [permissions.IsAuthenticated(), IsWorkspaceMember()]

    @extend_schema(responses={200: ArticleSEOSerializer})
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
        seo, _ = ArticleSEO.objects.get_or_create(article=article)
        return Response(ArticleSEOSerializer(seo).data, status=status.HTTP_200_OK)

    @extend_schema(request=ArticleSEOSerializer, responses={200: ArticleSEOSerializer})
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
        seo, _ = ArticleSEO.objects.get_or_create(article=article)

        serializer = ArticleSEOSerializer(
            seo, data=request.data, partial=True, context={"article": article}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        record_audit_event(
            action="seo.article_metadata_updated",
            request=request,
            workspace_id=workspace.id,
            resource_type="article_seo",
            resource_id=str(seo.id),
            payload={"article_id": str(article.id), "canonical_url": seo.canonical_url},
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class RedirectRuleListCreateView(APIView):
    """List or create redirect rules for a site (SEO-4)."""

    pagination_class = DefaultPagination

    def get_permissions(self) -> list[permissions.BasePermission]:
        if self.request.method == "POST":
            return [permissions.IsAuthenticated(), IsWorkspaceAdmin()]
        return [permissions.IsAuthenticated(), IsWorkspaceMember()]

    @extend_schema(responses={200: RedirectRuleSerializer(many=True)})
    def get(
        self, request: Request, workspace_id: str, site_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)
        rules = RedirectRule.objects.filter(site=site).order_by("source_path")

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(rules, request, view=self)
        if page is not None:
            serializer = RedirectRuleSerializer(page, many=True)
            return paginator.get_paginated_response(list(serializer.data))

        return Response(RedirectRuleSerializer(rules, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(request=RedirectRuleSerializer, responses={201: RedirectRuleSerializer})
    def post(
        self, request: Request, workspace_id: str, site_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)

        serializer = RedirectRuleSerializer(data=request.data, context={"site": site})
        serializer.is_valid(raise_exception=True)
        rule = serializer.save(site=site)

        record_audit_event(
            action="seo.redirect_created",
            request=request,
            workspace_id=workspace.id,
            resource_type="redirect",
            resource_id=str(rule.id),
            payload={"source": rule.source_path, "target": rule.target_url},
        )
        return Response(RedirectRuleSerializer(rule).data, status=status.HTTP_201_CREATED)


class RedirectRuleDetailView(APIView):
    """Retrieve, update, or delete a redirect rule (SEO-4)."""

    def get_permissions(self) -> list[permissions.BasePermission]:
        if self.request.method in ("PATCH", "PUT", "DELETE"):
            return [permissions.IsAuthenticated(), IsWorkspaceAdmin()]
        return [permissions.IsAuthenticated(), IsWorkspaceMember()]

    @extend_schema(
        responses={200: RedirectRuleSerializer, 404: OpenApiResponse(description="Rule not found")}
    )
    def get(
        self,
        request: Request,
        workspace_id: str,
        site_id: str,
        rule_id: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)
        rule = _get_redirect_rule(site, rule_id)
        return Response(RedirectRuleSerializer(rule).data, status=status.HTTP_200_OK)

    @extend_schema(request=RedirectRuleSerializer, responses={200: RedirectRuleSerializer})
    def patch(
        self,
        request: Request,
        workspace_id: str,
        site_id: str,
        rule_id: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)
        rule = _get_redirect_rule(site, rule_id)

        serializer = RedirectRuleSerializer(
            rule, data=request.data, partial=True, context={"site": site}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        record_audit_event(
            action="seo.redirect_updated",
            request=request,
            workspace_id=workspace.id,
            resource_type="redirect",
            resource_id=str(rule.id),
            payload={"source": rule.source_path, "target": rule.target_url},
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(responses={204: OpenApiResponse(description="Redirect rule deleted")})
    def delete(
        self,
        request: Request,
        workspace_id: str,
        site_id: str,
        rule_id: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)
        rule = _get_redirect_rule(site, rule_id)
        r_id = str(rule.id)
        source = rule.source_path
        rule.delete()

        record_audit_event(
            action="seo.redirect_deleted",
            request=request,
            workspace_id=workspace.id,
            resource_type="redirect",
            resource_id=r_id,
            payload={"source": source},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class SEOAuditView(APIView):
    """Run automated SEO diagnostics for all articles in a site (SEO-7)."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceMember)

    @extend_schema(responses={200: SEOAuditItemSerializer(many=True)})
    def get(
        self, request: Request, workspace_id: str, site_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)
        diagnostics = run_seo_audit(site)
        return Response(diagnostics, status=status.HTTP_200_OK)


class PublicSitemapXmlView(APIView):
    """Generate and serve XML sitemap for search indexing engines (SEO-5)."""

    permission_classes = (permissions.AllowAny,)
    authentication_classes = ()

    @extend_schema(
        responses={
            200: OpenApiResponse(description="XML sitemap document"),
            404: OpenApiResponse(description="Site not found"),
        }
    )
    def get(self, request: Request, site_slug: str, *args: Any, **kwargs: Any) -> HttpResponse:
        site = Site.objects.filter(slug=site_slug, is_active=True).first()
        if site is None:
            raise NotFound("Site not found or inactive.")

        xml_content = generate_sitemap_xml(site)
        response = HttpResponse(xml_content, content_type="application/xml; charset=utf-8")
        response["Cache-Control"] = "public, max-age=300"
        return response


class PublicRobotsTxtView(APIView):
    """Generate and serve robots.txt configuration with sitemap references (SEO-6)."""

    permission_classes = (permissions.AllowAny,)
    authentication_classes = ()

    @extend_schema(
        responses={
            200: OpenApiResponse(description="Plaintext robots.txt file"),
            404: OpenApiResponse(description="Site not found"),
        }
    )
    def get(self, request: Request, site_slug: str, *args: Any, **kwargs: Any) -> HttpResponse:
        site = Site.objects.filter(slug=site_slug, is_active=True).first()
        if site is None:
            raise NotFound("Site not found or inactive.")

        robots_content = generate_robots_txt(site)
        response = HttpResponse(robots_content, content_type="text/plain; charset=utf-8")
        response["Cache-Control"] = "public, max-age=300"
        return response


class PublicArticleSEOView(APIView):
    """Serve structured SEO metadata, canonicals, and JSON-LD for frontend rendering.

    Requirements satisfied: SEO-1, SEO-9.
    """

    permission_classes = (permissions.AllowAny,)
    authentication_classes = ()

    @extend_schema(
        responses={
            200: PublicSEOMetadataSerializer,
            404: OpenApiResponse(description="Article not found"),
        }
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
            raise NotFound("Article not found or not published.")

        seo_data = resolve_article_seo(article)
        response = Response(seo_data, status=status.HTTP_200_OK)

        etag = hashlib.sha256(f"{article.id}:{article.updated_at}:seo".encode()).hexdigest()
        response["ETag"] = f'"{etag}"'
        response["Cache-Control"] = "public, max-age=60"
        return response
