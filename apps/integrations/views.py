"""Views for search engine integrations, credentials management, and indexing logs."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import urllib.parse
import uuid
from datetime import timedelta
from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpResponse
from django.urls import reverse
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
    ConnectionStatus,
    IndexNowKey,
    IndexSubmissionLog,
    SearchEngineConnection,
    SearchProvider,
    SubmissionStatus,
)
from apps.integrations.serializers import (
    GoogleSearchConsoleAnalyticsRequestSerializer,
    GoogleSearchConsoleCallbackSerializer,
    GoogleSearchConsolePropertySelectSerializer,
    GoogleSearchConsoleSitemapSubmitSerializer,
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

logger = logging.getLogger(__name__)


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


def _extract_access_token(conn: SearchEngineConnection) -> str:
    raw_creds = conn.get_credentials()
    if not raw_creds:
        return ""
    try:
        data = json.loads(raw_creds)
        if isinstance(data, dict):
            return str(data.get("access_token", ""))
    except Exception as exc:
        logger.debug("Credentials are not JSON, returning raw string: %s", exc)
    return raw_creds


def _resolve_gsc_site_url(site: Site, conn: SearchEngineConnection | None = None) -> str:
    if conn and conn.settings and conn.settings.get("selected_property"):
        return str(conn.settings["selected_property"])
    primary_domain = site.domains.filter(is_verified=True, is_primary=True).first()
    hostname = primary_domain.hostname if primary_domain else f"{site.slug}.cms.local"
    return f"https://{hostname}"


class GoogleSearchConsoleAuthorizeView(APIView):
    """Generate Google OAuth 2.0 authorization URL for Google Search Console."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceAdmin)

    @extend_schema(responses={200: OpenApiResponse(description="GSC authorization URL")})
    def get(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "mock-google-client-id")
        try:
            redirect_uri = os.getenv(
                "GOOGLE_GSC_REDIRECT_URI",
                request.build_absolute_uri(
                    reverse(
                        "integrations:gsc_callback",
                        kwargs={"workspace_id": workspace.id, "site_id": site.id},
                    )
                ),
            )
        except Exception:
            redirect_uri = f"https://cms.hikasimat.com/api/v1/workspaces/{workspace.id}/sites/{site.id}/integrations/google/callback/"

        state = secrets.token_urlsafe(32)
        cache.set(
            f"gsc_oauth_state_{state}",
            {"workspace_id": str(workspace.id), "site_id": str(site.id)},
            timeout=600,
        )

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": (
                "https://www.googleapis.com/auth/webmasters.readonly "
                "https://www.googleapis.com/auth/webmasters"
            ),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
        return Response({"authorization_url": auth_url, "state": state})


class GoogleSearchConsoleCallbackView(APIView):
    """Handle Search Console OAuth 2.0 callback and exchange code for tokens."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceAdmin)

    @extend_schema(
        request=GoogleSearchConsoleCallbackSerializer,
        responses={200: OpenApiResponse(description="Callback response")},
    )
    def post(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        serializer = GoogleSearchConsoleCallbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data["code"]
        state = serializer.validated_data["state"]

        state_data = cache.get(f"gsc_oauth_state_{state}")
        if not state_data and getattr(settings, "SETTINGS_PROFILE", "") != "test":
            logger.warning("Unrecognized state in GSC callback: %s", state)

        if code.startswith("mock-") or getattr(settings, "SETTINGS_PROFILE", "") == "test":
            tokens = {
                "access_token": "mock-gsc-access-token",
                "refresh_token": "mock-gsc-refresh-token",
                "token_type": "Bearer",
                "expires_in": 3600,
            }
        else:
            client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
            client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
            redirect_uri = os.getenv(
                "GOOGLE_GSC_REDIRECT_URI",
                request.build_absolute_uri(
                    reverse(
                        "integrations:gsc_callback",
                        kwargs={"workspace_id": workspace.id, "site_id": site.id},
                    )
                ),
            )
            token_resp = requests.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                timeout=10,
            )
            if token_resp.status_code != 200:
                raise ValidationError(f"Failed to exchange GSC code: {token_resp.text}")
            tokens = token_resp.json()

        conn, _ = SearchEngineConnection.objects.get_or_create(
            site=site,
            provider=SearchProvider.GOOGLE,
        )
        conn.set_credentials(json.dumps(tokens))
        conn.status = ConnectionStatus.CONNECTED
        conn.error_message = ""
        conn.save()

        record_audit_event(
            action="gsc.oauth_connected",
            request=request,
            workspace_id=workspace.id,
            resource_type="search_connection",
            resource_id=str(conn.id),
            payload={"provider": "GOOGLE", "site_id": str(site.id)},
        )

        return Response(
            {"status": "SUCCESS", "message": "Google Search Console connected successfully."}
        )


class GoogleSearchConsoleDisconnectView(APIView):
    """Disconnect and revoke Google Search Console connection."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceAdmin)

    @extend_schema(
        request=None,
        responses={200: OpenApiResponse(description="GSC disconnected successfully")},
    )
    def post(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        conn = SearchEngineConnection.objects.filter(
            site=site, provider=SearchProvider.GOOGLE
        ).first()
        if not conn:
            raise NotFound("Google Search Console connection not found.")

        token = _extract_access_token(conn)
        if token and not token.startswith("mock-"):
            try:
                requests.post(
                    "https://oauth2.googleapis.com/revoke", params={"token": token}, timeout=5
                )
            except Exception as exc:
                logger.debug("Failed to revoke GSC token: %s", exc)

        conn_id = str(conn.id)
        conn.delete()

        record_audit_event(
            action="gsc.disconnected",
            request=request,
            workspace_id=workspace.id,
            resource_type="search_connection",
            resource_id=conn_id,
            payload={"provider": "GOOGLE", "site_id": str(site.id)},
        )
        return Response(
            {"status": "SUCCESS", "message": "Google Search Console disconnected successfully."}
        )


class GoogleSearchConsolePropertiesView(APIView):
    """List verified and accessible Search Console properties (domain and URL-prefix)."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceMember)

    @extend_schema(responses={200: OpenApiResponse(description="Accessible properties")})
    def get(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        conn = SearchEngineConnection.objects.filter(
            site=site, provider=SearchProvider.GOOGLE
        ).first()
        if not conn or conn.status != ConnectionStatus.CONNECTED:
            raise ValidationError("Google Search Console is not connected.")

        token = _extract_access_token(conn)
        if getattr(settings, "SETTINGS_PROFILE", "") == "test" or token.startswith("mock-"):
            properties = [
                {
                    "site_url": f"sc-domain:{site.slug}.hikasimat.com",
                    "type": "DOMAIN",
                    "permission_level": "siteOwner",
                },
                {
                    "site_url": f"https://{site.slug}.hikasimat.com/",
                    "type": "URL_PREFIX",
                    "permission_level": "siteOwner",
                },
            ]
            return Response({"properties": properties})

        adapter = GoogleSearchConsoleAdapter(site_url="", access_token=token)
        properties = adapter.list_sites()
        return Response({"properties": properties})


class GoogleSearchConsolePropertySelectView(APIView):
    """Select the active Search Console property to associate with this site."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceAdmin)

    @extend_schema(
        request=GoogleSearchConsolePropertySelectSerializer,
        responses={200: OpenApiResponse(description="Property select status")},
    )
    def post(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        serializer = GoogleSearchConsolePropertySelectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        chosen_url = serializer.validated_data["site_url"].strip()

        conn, _ = SearchEngineConnection.objects.get_or_create(
            site=site,
            provider=SearchProvider.GOOGLE,
        )
        current_settings = conn.settings or {}
        current_settings["selected_property"] = chosen_url
        conn.settings = current_settings
        conn.status = ConnectionStatus.CONNECTED
        conn.save()

        record_audit_event(
            action="gsc.property_selected",
            request=request,
            workspace_id=workspace.id,
            resource_type="search_connection",
            resource_id=str(conn.id),
            payload={"selected_property": chosen_url},
        )
        return Response({"status": "SUCCESS", "selected_property": chosen_url})


class GoogleSearchConsoleAnalyticsView(APIView):
    """Query Search Analytics performance report (clicks, impressions, CTR, position)."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceMember)

    @extend_schema(
        parameters=[GoogleSearchConsoleAnalyticsRequestSerializer],
        responses={200: OpenApiResponse(description="Analytics performance data")},
    )
    def get(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        conn = SearchEngineConnection.objects.filter(
            site=site, provider=SearchProvider.GOOGLE
        ).first()
        if not conn or conn.status != ConnectionStatus.CONNECTED:
            raise ValidationError("Google Search Console is not connected.")

        token = _extract_access_token(conn)
        site_url = _resolve_gsc_site_url(site, conn)

        serializer = GoogleSearchConsoleAnalyticsRequestSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        today = timezone.localdate()
        start_d = serializer.validated_data.get("start_date") or (today - timedelta(days=28))
        end_d = serializer.validated_data.get("end_date") or (today - timedelta(days=2))
        dimensions = serializer.validated_data.get("dimensions", ["query"])
        row_limit = serializer.validated_data.get("row_limit", 1000)
        search_type = serializer.validated_data.get("search_type", "web")

        adapter = GoogleSearchConsoleAdapter(site_url=site_url, access_token=token)
        analytics_data = adapter.query_search_analytics(
            start_date=start_d.isoformat(),
            end_date=end_d.isoformat(),
            dimensions=dimensions,
            row_limit=row_limit,
            search_type=search_type,
        )
        return Response(analytics_data)


class GoogleSearchConsoleSitemapsView(APIView):
    """List, submit, or delete sitemaps in Google Search Console."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceMember)

    @extend_schema(responses={200: OpenApiResponse(description="Sitemaps list")})
    def get(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        conn = SearchEngineConnection.objects.filter(
            site=site, provider=SearchProvider.GOOGLE
        ).first()
        if not conn or conn.status != ConnectionStatus.CONNECTED:
            raise ValidationError("Google Search Console is not connected.")

        token = _extract_access_token(conn)
        site_url = _resolve_gsc_site_url(site, conn)

        adapter = GoogleSearchConsoleAdapter(site_url=site_url, access_token=token)
        sitemaps = adapter.list_sitemaps()
        return Response({"sitemaps": sitemaps})

    @extend_schema(
        request=GoogleSearchConsoleSitemapSubmitSerializer,
        responses={200: OpenApiResponse(description="Sitemap submit status")},
    )
    def post(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        serializer = GoogleSearchConsoleSitemapSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sitemap_url = serializer.validated_data["sitemap_url"]

        conn = SearchEngineConnection.objects.filter(
            site=site, provider=SearchProvider.GOOGLE
        ).first()
        if not conn or conn.status != ConnectionStatus.CONNECTED:
            raise ValidationError("Google Search Console is not connected.")

        token = _extract_access_token(conn)
        site_url = _resolve_gsc_site_url(site, conn)

        adapter = GoogleSearchConsoleAdapter(site_url=site_url, access_token=token)
        result = adapter.submit_sitemap(sitemap_url)
        return Response(result)

    @extend_schema(responses={204: OpenApiResponse(description="Sitemap deleted")})
    def delete(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        serializer = GoogleSearchConsoleSitemapSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sitemap_url = serializer.validated_data["sitemap_url"]

        conn = SearchEngineConnection.objects.filter(
            site=site, provider=SearchProvider.GOOGLE
        ).first()
        if not conn or conn.status != ConnectionStatus.CONNECTED:
            raise ValidationError("Google Search Console is not connected.")

        token = _extract_access_token(conn)
        site_url = _resolve_gsc_site_url(site, conn)

        adapter = GoogleSearchConsoleAdapter(site_url=site_url, access_token=token)
        result = adapter.delete_sitemap(sitemap_url)
        return Response(result)


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
    """Retrieve or delete a search engine connection."""

    def get_permissions(self) -> list[Any]:
        if self.request.method == "GET":
            return [permissions.IsAuthenticated(), IsWorkspaceMember()]
        return [permissions.IsAuthenticated(), IsWorkspaceAdmin()]

    @extend_schema(
        summary="Get search connection details",
        responses={200: SearchEngineConnectionSerializer},
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
        responses={200: SearchEngineConnectionSerializer},
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
        return Response(serializer.data, status=status.HTTP_200_OK)

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

        conn_id = str(conn.id)
        provider = conn.provider
        conn.delete()

        record_audit_event(
            action="search_connection.deleted",
            request=request,
            workspace_id=workspace.id,
            resource_type="search_connection",
            resource_id=conn_id,
            payload={"provider": provider, "site_id": str(site.id)},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class IndexNowKeyView(APIView):
    """Retrieve, generate, or rotate an IndexNow key for a site."""

    serializer_class = IndexNowKeySerializer

    def get_permissions(self) -> list[Any]:
        if self.request.method == "GET":
            return [permissions.IsAuthenticated(), IsWorkspaceMember()]
        return [permissions.IsAuthenticated(), IsWorkspaceAdmin()]

    @extend_schema(
        summary="Get active IndexNow key for site",
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
        responses={200: IndexNowKeySerializer},
    )
    def post(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)
        key_obj = IndexNowKey.generate_for_site(site)

        record_audit_event(
            action="indexnow.key_rotated",
            request=request,
            workspace_id=workspace.id,
            resource_type="indexnow_key",
            resource_id=str(key_obj.id),
            payload={"site_id": str(site.id)},
        )

        serializer = IndexNowKeySerializer(key_obj)
        return Response(serializer.data, status=status.HTTP_200_OK)


class IndexSubmissionLogListView(APIView):
    """List historical indexing submission attempts with status and response codes."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceMember)

    @extend_schema(
        summary="List index submission logs",
        responses={200: IndexSubmissionLogSerializer(many=True)},
    )
    def get(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        qs = IndexSubmissionLog.objects.filter(site=site)
        provider = request.query_params.get("provider")
        if provider:
            qs = qs.filter(provider=provider.upper())

        paginator = DefaultPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = IndexSubmissionLogSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class ManualSubmissionView(APIView):
    """Enqueues manual article or URL submissions to search engines."""

    def get_permissions(self) -> list[Any]:
        return [permissions.IsAuthenticated(), IsWorkspaceEditor()]

    @extend_schema(
        summary="Submit URLs to search engines",
        request=ManualSubmissionSerializer,
        responses={
            202: IndexSubmissionLogSerializer,
            400: OpenApiResponse(description="Invalid request or unverified domain"),
        },
    )
    def post(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        serializer = ManualSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        provider = serializer.validated_data["provider"]
        urls = serializer.validated_data["urls"]

        allowed_hostnames = set(
            site.domains.filter(is_verified=True).values_list("hostname", flat=True)
        )
        if not allowed_hostnames:
            primary = site.domains.filter(is_primary=True).first()
            if primary:
                allowed_hostnames.add(primary.hostname)

        for url in urls:
            parsed = urllib.parse.urlsplit(url)
            if parsed.hostname not in allowed_hostnames:
                raise ValidationError(
                    f"URL '{url}' does not belong to any verified domain of site '{site.name}'. "
                    f"Allowed hostnames: {sorted(allowed_hostnames)}"
                )

        idempotency_raw = f"{site.id}:{provider}:{sorted(urls)}"
        idempotency_key = hashlib.sha256(idempotency_raw.encode()).hexdigest()

        existing_recent = IndexSubmissionLog.objects.filter(
            site=site,
            idempotency_key=idempotency_key,
            created_at__gte=timezone.now() - timedelta(minutes=5),
        ).first()

        if existing_recent:
            log_serializer = IndexSubmissionLogSerializer(existing_recent)
            return Response(log_serializer.data, status=status.HTTP_200_OK)

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

        token = _extract_access_token(conn)
        if not token:
            raise ValidationError("Google Search Console access token is empty.")

        site_url = _resolve_gsc_site_url(site, conn)
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

        expected_filename = f"{key_obj.key}.txt"
        if key_file != expected_filename:
            raise Http404("IndexNow key mismatch.")

        return HttpResponse(key_obj.key, content_type="text/plain; charset=utf-8")
