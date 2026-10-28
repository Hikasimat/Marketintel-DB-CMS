"""Views for search engine integrations, credentials management, and indexing logs."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from django.http import Http404, HttpResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit_event
from apps.common.pagination import DefaultPagination
from apps.integrations.adapters.google import GoogleSearchConsoleAdapter
from apps.integrations.models import (
    IndexNowKey,
    IndexSubmissionLog,
    SearchEngineConnection,
    SearchProvider,
    SubmissionStatus,
)
from apps.integrations.serializers import (
    IndexNowKeySerializer,
    IndexSubmissionLogSerializer,
    ManualSubmissionSerializer,
    SearchEngineConnectionSerializer,
    UrlInspectionRequestSerializer,
)
from apps.integrations.tasks import submit_indexing_job
from apps.sites.models import Site
from apps.sites.views import _get_site
from apps.tenancy.permissions import (
    IsWorkspaceAdmin,
    IsWorkspaceEditor,
    IsWorkspaceMember,
    resolve_workspace,
)


def _get_connection(site: Site, connection_id: Any) -> SearchEngineConnection:
    if isinstance(connection_id, uuid.UUID):
        c_id = connection_id
    else:
        try:
            c_id = uuid.UUID(str(connection_id))
        except ValueError as exc:
            raise NotFound("Search engine connection not found.") from exc

    conn = SearchEngineConnection.objects.filter(site=site, id=c_id).first()
    if conn is None:
        raise NotFound("Search engine connection not found.")
    return conn


class SearchConnectionListCreateView(APIView):
    """List or configure search engine API connections for a site (SEC-3)."""

    def get_permissions(self) -> list[Any]:
        if self.request.method == "GET":
            return [permissions.IsAuthenticated(), IsWorkspaceMember()]
        return [permissions.IsAuthenticated(), IsWorkspaceAdmin()]

    @extend_schema(
        summary="List search engine connections for site",
        responses={200: SearchEngineConnectionSerializer(many=True)},
    )
    def get(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)
        connections = SearchEngineConnection.objects.filter(site=site)
        serializer = SearchEngineConnectionSerializer(connections, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Configure or update search engine connection",
        request=SearchEngineConnectionSerializer,
        responses={
            201: SearchEngineConnectionSerializer,
            400: OpenApiResponse(description="Invalid data"),
        },
    )
    def post(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        provider = request.data.get("provider") if isinstance(request.data, dict) else None
        existing = SearchEngineConnection.objects.filter(site=site, provider=provider).first()

        serializer = SearchEngineConnectionSerializer(
            instance=existing, data=request.data, partial=bool(existing)
        )
        serializer.is_valid(raise_exception=True)
        conn = serializer.save(site=site)

        record_audit_event(
            action="search_connection.configured",
            request=request,
            workspace_id=workspace.id,
            resource_type="search_connection",
            resource_id=str(conn.id),
            payload={"provider": conn.provider, "site_id": str(site.id)},
        )
        status_code = status.HTTP_200_OK if existing else status.HTTP_201_CREATED
        return Response(serializer.data, status=status_code)


class SearchConnectionDetailView(APIView):
    """Retrieve, update, or remove a specific search engine connection."""

    def get_permissions(self) -> list[Any]:
        if self.request.method == "GET":
            return [permissions.IsAuthenticated(), IsWorkspaceMember()]
        return [permissions.IsAuthenticated(), IsWorkspaceAdmin()]

    @extend_schema(
        summary="Get search connection details",
        responses={
            200: SearchEngineConnectionSerializer,
            404: OpenApiResponse(description="Not found"),
        },
    )
    def get(
        self, request: Request, workspace_id: Any, site_id: Any, connection_id: Any
    ) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)
        conn = _get_connection(site, connection_id)
        serializer = SearchEngineConnectionSerializer(conn)
        return Response(serializer.data)

    @extend_schema(
        summary="Update search engine connection",
        request=SearchEngineConnectionSerializer,
        responses={
            200: SearchEngineConnectionSerializer,
            400: OpenApiResponse(description="Invalid data"),
        },
    )
    def patch(
        self, request: Request, workspace_id: Any, site_id: Any, connection_id: Any
    ) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)
        conn = _get_connection(site, connection_id)

        serializer = SearchEngineConnectionSerializer(conn, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_conn = serializer.save()

        record_audit_event(
            action="search_connection.updated",
            request=request,
            workspace_id=workspace.id,
            resource_type="search_connection",
            resource_id=str(updated_conn.id),
            payload={"provider": updated_conn.provider, "site_id": str(site.id)},
        )
        return Response(serializer.data)

    @extend_schema(
        summary="Delete search engine connection",
        responses={204: OpenApiResponse(description="Deleted")},
    )
    def delete(
        self, request: Request, workspace_id: Any, site_id: Any, connection_id: Any
    ) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)
        conn = _get_connection(site, connection_id)
        provider = conn.provider
        conn_id = conn.id
        conn.delete()

        record_audit_event(
            action="search_connection.deleted",
            request=request,
            workspace_id=workspace.id,
            resource_type="search_connection",
            resource_id=str(conn_id),
            payload={"provider": provider, "site_id": str(site.id)},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class IndexNowKeyView(APIView):
    """Retrieve or generate IndexNow verification key for site."""

    def get_permissions(self) -> list[Any]:
        return [permissions.IsAuthenticated(), IsWorkspaceMember()]

    @extend_schema(
        summary="Get or generate IndexNow key for site",
        responses={200: IndexNowKeySerializer},
    )
    def get(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        try:
            key_obj = site.indexnow_key
        except IndexNowKey.DoesNotExist:
            key_obj = IndexNowKey.generate_for_site(site)

        serializer = IndexNowKeySerializer(key_obj)
        return Response(serializer.data)

    @extend_schema(
        summary="Rotate IndexNow key for site",
        request=None,
        responses={200: IndexNowKeySerializer},
    )
    def post(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        new_key = IndexNowKey.generate_for_site(site)
        record_audit_event(
            action="indexnow.rotated",
            request=request,
            workspace_id=workspace.id,
            resource_type="indexnow_key",
            resource_id=str(new_key.id),
            payload={"site_id": str(site.id), "key": new_key.key},
        )
        serializer = IndexNowKeySerializer(new_key)
        return Response(serializer.data)


class IndexSubmissionLogListView(APIView):
    """List search engine indexing submission logs for site."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceMember)

    @extend_schema(
        summary="List indexing submission logs",
        responses={200: IndexSubmissionLogSerializer(many=True)},
    )
    def get(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        logs = IndexSubmissionLog.objects.filter(site=site)
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(logs, request, view=self)
        serializer = IndexSubmissionLogSerializer(page, many=True)
        return paginator.get_paginated_response(list(serializer.data))


class ManualSubmissionView(APIView):
    """Manually submit article or page URLs to search engines (OPS-1)."""

    def get_permissions(self) -> list[Any]:
        return [permissions.IsAuthenticated(), IsWorkspaceEditor()]

    @extend_schema(
        summary="Submit URLs to search provider",
        request=ManualSubmissionSerializer,
        responses={
            202: IndexSubmissionLogSerializer,
            400: OpenApiResponse(description="Invalid request"),
        },
    )
    def post(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        serializer = ManualSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        provider = serializer.validated_data["provider"]
        urls = serializer.validated_data["urls"]

        # Validate that URLs belong to site domains
        registered_hostnames = set(site.domains.values_list("hostname", flat=True))
        if not registered_hostnames:
            registered_hostnames.add(f"{site.slug}.cms.local")

        for u in urls:
            from urllib.parse import urlparse

            parsed = urlparse(u)
            if parsed.hostname and parsed.hostname not in registered_hostnames:
                raise ValidationError(
                    f"URL '{u}' does not match any registered domain for this site."
                )

        # Build idempotency key
        raw_key = (
            f"{site.id}:{provider}:{','.join(sorted(urls))}:{timezone.now().strftime('%Y%m%d%H%M')}"
        )
        idempotency_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

        log = IndexSubmissionLog.objects.create(
            site=site,
            provider=provider,
            urls=urls,
            idempotency_key=idempotency_key,
            status=SubmissionStatus.PENDING,
        )

        submit_indexing_job.delay(str(log.id))

        record_audit_event(
            action="search_submission.manual",
            request=request,
            workspace_id=workspace.id,
            resource_type="index_submission_log",
            resource_id=str(log.id),
            payload={"provider": provider, "count": len(urls), "site_id": str(site.id)},
        )

        log_serializer = IndexSubmissionLogSerializer(log)
        return Response(log_serializer.data, status=status.HTTP_202_ACCEPTED)


class UrlInspectionView(APIView):
    """Inspect URL status using Google Search Console URL Inspection API."""

    def get_permissions(self) -> list[Any]:
        return [permissions.IsAuthenticated(), IsWorkspaceMember()]

    @extend_schema(
        summary="Inspect URL indexing status via Google Search Console",
        request=UrlInspectionRequestSerializer,
        responses={200: OpenApiResponse(description="Inspection details")},
    )
    def post(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        serializer = UrlInspectionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        url = serializer.validated_data["url"]

        conn = SearchEngineConnection.objects.filter(
            site=site, provider=SearchProvider.GOOGLE
        ).first()
        if not conn:
            raise ValidationError("Google Search Console connection not configured for this site.")

        token = conn.get_credentials()
        if not token:
            raise ValidationError("Google Search Console access token is empty.")

        primary_domain = site.domains.filter(is_verified=True, is_primary=True).first()
        hostname = primary_domain.hostname if primary_domain else f"{site.slug}.cms.local"
        site_url = f"https://{hostname}"

        adapter = GoogleSearchConsoleAdapter(site_url=site_url, access_token=token)
        inspection_data = adapter.inspect_url(url)

        return Response(inspection_data)


class PublicIndexNowKeyFileView(APIView):
    """Public endpoint to serve the IndexNow verification key file (e.g. /<key>.txt)."""

    permission_classes = (permissions.AllowAny,)

    @extend_schema(
        summary="IndexNow key file delivery",
        responses={
            200: OpenApiResponse(description="IndexNow key text"),
            404: OpenApiResponse(description="Key not found"),
        },
    )
    def get(self, request: Request, site_slug: str, key_file: str) -> HttpResponse:
        site = Site.objects.filter(slug=site_slug).first()
        if not site:
            raise Http404("Site not found.")

        try:
            key_obj = site.indexnow_key
        except IndexNowKey.DoesNotExist as exc:
            raise Http404("IndexNow key not configured.") from exc

        # Expect key_file to be <key>.txt
        expected_filename = f"{key_obj.key}.txt"
        if key_file != expected_filename:
            raise Http404("IndexNow key mismatch.")

        return HttpResponse(key_obj.key, content_type="text/plain; charset=utf-8")
