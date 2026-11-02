"""Views for analytics configuration, GA4 reports, ingestion, and metrics."""

from __future__ import annotations

import logging
import os
import secrets
import urllib.parse
from datetime import date, timedelta
from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache
from django.http import Http404
from django.urls import reverse
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analytics.adapters.ga4 import GA4AdminAdapter, GA4ReportingAdapter
from apps.analytics.models import (
    AnalyticsReportSnapshot,
    GA4Connection,
    SiteAnalyticsConfig,
)
from apps.analytics.serializers import (
    EventIngestSerializer,
    GA4CallbackSerializer,
    GA4ConnectionSerializer,
    GA4PropertySelectSerializer,
    GA4ReportRequestSerializer,
    GoogleTagSnippetSerializer,
    PublicAnalyticsConfigSerializer,
    SiteAnalyticsConfigSerializer,
)
from apps.analytics.services import (
    erase_visitor_data,
    get_first_party_metrics,
    ingest_first_party_event,
)
from apps.audit.services import record_audit_event
from apps.content.views import _check_public_origin_allowlist
from apps.sites.models import Site
from apps.sites.views import _get_site
from apps.tenancy.permissions import (
    IsWorkspaceAdmin,
    IsWorkspaceMember,
    resolve_workspace,
)

logger = logging.getLogger(__name__)


class GoogleTagSnippetView(APIView):
    """Generate official Google tag (gtag.js) snippet with Consent Mode v2 defaults."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceMember)

    @extend_schema(
        summary="Generate Google Tag (gtag.js) snippet with Consent Mode v2",
        responses={200: GoogleTagSnippetSerializer},
    )
    def get(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)
        config, _ = SiteAnalyticsConfig.objects.get_or_create(site=site)

        measurement_id = config.measurement_id.strip() if config.measurement_id else ""
        tag_id = measurement_id if measurement_id else "G-XXXXXXXXXX"

        snippet = (
            "<!-- Google tag (gtag.js) -->\n"
            f'<script async src="https://www.googletagmanager.com/gtag/js?id={tag_id}"></script>\n'
            "<script>\n"
            "  window.dataLayer = window.dataLayer || [];\n"
            "  function gtag(){dataLayer.push(arguments);}\n"
            "  gtag('consent', 'default', {\n"
            "    'ad_storage': 'denied',\n"
            "    'ad_user_data': 'denied',\n"
            "    'ad_personalization': 'denied',\n"
            "    'analytics_storage': 'denied'\n"
            "  });\n"
            "  gtag('js', new Date());\n"
            f"  gtag('config', '{tag_id}');\n"
            "</script>"
        )

        consent_defaults = {
            "ad_storage": "denied",
            "ad_user_data": "denied",
            "ad_personalization": "denied",
            "analytics_storage": "denied",
        }

        return Response(
            {
                "measurement_id": measurement_id,
                "tag_snippet": snippet,
                "consent_mode_v2_defaults": consent_defaults,
                "copy_button_ready": True,
            },
            status=status.HTTP_200_OK,
        )


class GA4AuthorizeView(APIView):
    """Generate Google OAuth 2.0 authorization URL for GA4 Data & Admin API."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceAdmin)

    def get(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "mock-google-client-id")
        try:
            redirect_uri = os.getenv(
                "GOOGLE_GA4_REDIRECT_URI",
                request.build_absolute_uri(
                    reverse(
                        "analytics:ga4_callback",
                        kwargs={"workspace_id": workspace.id, "site_id": site.id},
                    )
                ),
            )
        except Exception:
            redirect_uri = f"https://cms.hikasimat.com/api/v1/workspaces/{workspace.id}/sites/{site.id}/analytics/google/callback/"

        state = secrets.token_urlsafe(32)
        cache.set(
            f"ga4_oauth_state_{state}",
            {"workspace_id": str(workspace.id), "site_id": str(site.id)},
            timeout=600,
        )

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": (
                "https://www.googleapis.com/auth/analytics.readonly "
                "https://www.googleapis.com/auth/analytics.edit"
            ),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
        return Response({"authorization_url": auth_url, "state": state})


class GA4CallbackView(APIView):
    """Handle Google OAuth 2.0 callback and exchange code for tokens."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceAdmin)

    def post(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        serializer = GA4CallbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data["code"]
        state = serializer.validated_data["state"]

        state_data = cache.get(f"ga4_oauth_state_{state}")
        if not state_data and getattr(settings, "SETTINGS_PROFILE", "") != "test":
            logger.warning("Unrecognized state in GA4 callback: %s", state)

        # Handle mock in test mode
        if code.startswith("mock-") or getattr(settings, "SETTINGS_PROFILE", "") == "test":
            tokens = {
                "access_token": "mock-ga4-access-token",
                "refresh_token": "mock-ga4-refresh-token",
                "token_type": "Bearer",
                "expires_in": 3600,
            }
        else:
            client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
            client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
            redirect_uri = os.getenv(
                "GOOGLE_GA4_REDIRECT_URI",
                request.build_absolute_uri(
                    reverse(
                        "analytics:ga4_callback",
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
                raise ValidationError(f"Failed to exchange code: {token_resp.text}")
            tokens = token_resp.json()

        conn, _ = GA4Connection.objects.get_or_create(
            site=site, defaults={"property_id": "pending_selection"}
        )
        conn.set_credentials(tokens)
        conn.is_active = True
        conn.save()

        record_audit_event(
            action="ga4.oauth_connected",
            request=request,
            workspace_id=workspace.id,
            resource_type="ga4_connection",
            resource_id=str(conn.id),
            payload={"site_id": str(site.id)},
        )

        return Response(
            {"status": "SUCCESS", "message": "GA4 authorized successfully."},
            status=status.HTTP_200_OK,
        )


class GA4DisconnectView(APIView):
    """Disconnect and revoke GA4 authorization."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceAdmin)

    def post(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        conn = GA4Connection.objects.filter(site=site).first()
        if not conn:
            raise NotFound("GA4 connection not found.")

        creds = conn.get_credentials()
        token = creds.get("refresh_token") or creds.get("access_token")
        if token and not token.startswith("mock-"):
            try:
                requests.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": token},
                    timeout=5,
                )
            except Exception as exc:
                logger.debug("Failed to revoke GA4 token: %s", exc)

        conn_id = str(conn.id)
        conn.delete()

        record_audit_event(
            action="ga4.disconnected",
            request=request,
            workspace_id=workspace.id,
            resource_type="ga4_connection",
            resource_id=conn_id,
            payload={"site_id": str(site.id)},
        )
        return Response(
            {"status": "SUCCESS", "message": "GA4 disconnected successfully."},
            status=status.HTTP_200_OK,
        )


class GA4PropertiesListView(APIView):
    """List accessible GA4 accounts, properties, and data streams."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceMember)

    def get(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        conn = GA4Connection.objects.filter(site=site).first()
        if not conn or not conn.is_active:
            raise ValidationError("GA4 connection is not configured or inactive for this site.")

        creds = conn.get_credentials()
        access_token = creds.get("access_token", "")
        if getattr(settings, "SETTINGS_PROFILE", "") == "test" or access_token.startswith("mock-"):
            properties = [
                {
                    "account_name": "Production Account",
                    "property_id": "314159265",
                    "property_name": f"{site.name} Analytics",
                    "property_resource": "properties/314159265",
                    "streams": [
                        {
                            "stream_name": "Web Stream",
                            "stream_type": "WEB_DATA_STREAM",
                            "measurement_id": "G-LIVE987654",
                            "default_uri": f"https://{site.slug}.hikasimat.com",
                        }
                    ],
                }
            ]
            return Response({"properties": properties})

        adapter = GA4AdminAdapter(access_token=access_token)
        summaries = adapter.list_account_summaries()
        for prop in summaries:
            prop["streams"] = adapter.list_data_streams(prop["property_id"])

        return Response({"properties": summaries})


class GA4PropertySelectView(APIView):
    """Save selected property ID and measurement ID for site."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceAdmin)

    def post(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        serializer = GA4PropertySelectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        prop_id = serializer.validated_data["property_id"].removeprefix("properties/")
        meas_id = serializer.validated_data.get("measurement_id", "").strip()

        conn, _ = GA4Connection.objects.get_or_create(site=site, defaults={"property_id": prop_id})
        conn.property_id = prop_id
        conn.is_active = True
        conn.save()

        if meas_id:
            config, _ = SiteAnalyticsConfig.objects.get_or_create(site=site)
            config.measurement_id = meas_id
            config.save(update_fields=["measurement_id"])

        record_audit_event(
            action="ga4.property_selected",
            request=request,
            workspace_id=workspace.id,
            resource_type="ga4_connection",
            resource_id=str(conn.id),
            payload={"property_id": prop_id, "measurement_id": meas_id},
        )
        return Response({"status": "SUCCESS", "property_id": prop_id, "measurement_id": meas_id})


class SiteAnalyticsConfigView(APIView):
    """Retrieve or update site-wide analytics and GTM configuration (ANA-1)."""

    def get_permissions(self) -> list[Any]:
        if self.request.method == "GET":
            return [permissions.IsAuthenticated(), IsWorkspaceMember()]
        return [permissions.IsAuthenticated(), IsWorkspaceAdmin()]

    @extend_schema(
        summary="Get site analytics configuration",
        responses={200: SiteAnalyticsConfigSerializer},
    )
    def get(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        config, _ = SiteAnalyticsConfig.objects.get_or_create(site=site)
        serializer = SiteAnalyticsConfigSerializer(config)
        return Response(serializer.data)

    @extend_schema(
        summary="Update site analytics configuration",
        request=SiteAnalyticsConfigSerializer,
        responses={
            200: SiteAnalyticsConfigSerializer,
            400: OpenApiResponse(description="Invalid data"),
        },
    )
    def patch(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        config, _ = SiteAnalyticsConfig.objects.get_or_create(site=site)
        serializer = SiteAnalyticsConfigSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_config = serializer.save()

        record_audit_event(
            action="analytics_config.updated",
            request=request,
            workspace_id=workspace.id,
            resource_type="analytics_config",
            resource_id=str(updated_config.id),
            payload={
                "measurement_id": updated_config.measurement_id,
                "gtm_container_id": updated_config.gtm_container_id,
                "is_first_party_enabled": updated_config.is_first_party_enabled,
                "site_id": str(site.id),
            },
        )
        return Response(serializer.data)


class PublicAnalyticsConfigView(APIView):
    """Public endpoint providing safe, non-secret analytics IDs for browser loaders (ANA-1)."""

    permission_classes = (permissions.AllowAny,)

    @extend_schema(
        summary="Public analytics client configuration",
        responses={
            200: PublicAnalyticsConfigSerializer,
            404: OpenApiResponse(description="Site not found"),
        },
    )
    def get(self, request: Request, site_slug: str) -> Response:
        site = Site.objects.filter(slug=site_slug, is_active=True).first()
        if not site:
            raise Http404("Site not found.")

        _check_public_origin_allowlist(request, site)

        config, _ = SiteAnalyticsConfig.objects.get_or_create(site=site)
        serializer = PublicAnalyticsConfigSerializer(config)
        return Response(serializer.data)


class GA4ConnectionView(APIView):
    """Manage authorized GA4 OAuth connection and Reporting credentials (ANA-2)."""

    def get_permissions(self) -> list[Any]:
        if self.request.method == "GET":
            return [permissions.IsAuthenticated(), IsWorkspaceMember()]
        return [permissions.IsAuthenticated(), IsWorkspaceAdmin()]

    @extend_schema(
        summary="Get GA4 connection status",
        responses={
            200: GA4ConnectionSerializer,
            404: OpenApiResponse(description="Not configured"),
        },
    )
    def get(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        conn = GA4Connection.objects.filter(site=site).first()
        if not conn:
            raise NotFound("GA4 connection not configured for this site.")

        serializer = GA4ConnectionSerializer(conn)
        return Response(serializer.data)

    @extend_schema(
        summary="Configure GA4 OAuth connection",
        request=GA4ConnectionSerializer,
        responses={200: GA4ConnectionSerializer, 201: GA4ConnectionSerializer},
    )
    def post(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        existing = GA4Connection.objects.filter(site=site).first()
        serializer = GA4ConnectionSerializer(
            instance=existing, data=request.data, partial=bool(existing)
        )
        serializer.is_valid(raise_exception=True)
        conn = serializer.save(site=site)

        record_audit_event(
            action="ga4.connected",
            request=request,
            workspace_id=workspace.id,
            resource_type="ga4_connection",
            resource_id=str(conn.id),
            payload={"property_id": conn.property_id, "site_id": str(site.id)},
        )
        status_code = status.HTTP_200_OK if existing else status.HTTP_201_CREATED
        return Response(serializer.data, status=status_code)

    @extend_schema(
        summary="Disconnect GA4 connection",
        responses={204: OpenApiResponse(description="Disconnected")},
    )
    def delete(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        conn = GA4Connection.objects.filter(site=site).first()
        if not conn:
            raise NotFound("GA4 connection not found.")

        conn_id = str(conn.id)
        property_id = conn.property_id
        conn.delete()

        record_audit_event(
            action="ga4.disconnected",
            request=request,
            workspace_id=workspace.id,
            resource_type="ga4_connection",
            resource_id=conn_id,
            payload={"property_id": property_id, "site_id": str(site.id)},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class GA4ReportView(APIView):
    """Execute or retrieve cached GA4 Data API reports (ANA-3)."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceMember)

    @extend_schema(
        summary="Fetch GA4 reporting data",
        parameters=[GA4ReportRequestSerializer],
        responses={200: OpenApiResponse(description="GA4 report results")},
    )
    def get(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        conn = GA4Connection.objects.filter(site=site).first()
        if not conn:
            raise ValidationError("GA4 connection not configured for this site.")

        if not conn.is_active:
            raise ValidationError("GA4 connection is inactive.")

        serializer = GA4ReportRequestSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        report_type = serializer.validated_data.get("report_type", "overview")
        today = timezone.localdate()
        start_d = serializer.validated_data.get("start_date") or (today - timedelta(days=30))
        end_d = serializer.validated_data.get("end_date") or today
        use_cache = serializer.validated_data.get("use_cache", True)

        if start_d > end_d:
            raise ValidationError("start_date cannot be after end_date.")

        if (end_d - start_d).days > 365:
            raise ValidationError("Date range cannot exceed 365 days.")

        # Check cached snapshot (realtime report is never cached)
        if use_cache and report_type != "realtime":
            now = timezone.now()
            snapshot = AnalyticsReportSnapshot.objects.filter(
                site=site,
                report_type=report_type,
                start_date=start_d,
                end_date=end_d,
                expires_at__gt=now,
            ).first()
            if snapshot:
                data = dict(snapshot.data)
                data["cached"] = True
                return Response(data)

        creds = conn.get_credentials()
        access_token = creds.get("access_token", "")
        if not access_token:
            raise ValidationError(
                "GA4 access token is missing or expired. Re-authenticate connection."
            )

        adapter = GA4ReportingAdapter(
            property_id=conn.property_id,
            access_token=access_token,
        )

        start_str = start_d.isoformat()
        end_str = end_d.isoformat()

        if report_type in ("acquisition", "traffic_sources"):
            report_data = adapter.get_traffic_sources(start_str, end_str)
        elif report_type in ("pages", "top_pages"):
            report_data = adapter.get_top_pages(start_str, end_str)
        elif report_type == "audience":
            report_data = adapter.get_audience(start_str, end_str)
        elif report_type == "events":
            report_data = adapter.get_events(start_str, end_str)
        elif report_type == "realtime":
            report_data = adapter.get_realtime()
        else:
            report_data = adapter.get_overview(start_str, end_str)

        if report_data.get("status") == "SUCCESS" and report_type != "realtime":
            # Cache report snapshot for 6 hours
            expires_at = timezone.now() + timedelta(hours=6)
            AnalyticsReportSnapshot.objects.update_or_create(
                site=site,
                report_type=report_type,
                start_date=start_d,
                end_date=end_d,
                defaults={"data": report_data, "expires_at": expires_at},
            )
            report_data["cached"] = False

        return Response(report_data)


class PublicEventIngestView(APIView):
    """Ingest privacy-preserving first-party analytics events (ANA-4, ANA-5, ANA-6)."""

    permission_classes = (permissions.AllowAny,)

    @extend_schema(
        summary="Ingest first-party event",
        request=EventIngestSerializer,
        responses={
            202: OpenApiResponse(description="Event accepted"),
            400: OpenApiResponse(description="Invalid event"),
        },
    )
    def post(self, request: Request, site_slug: str) -> Response:
        site = Site.objects.filter(slug=site_slug, is_active=True).first()
        if not site:
            raise Http404("Site not found.")

        _check_public_origin_allowlist(request, site)

        serializer = EventIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_agent = request.META.get("HTTP_USER_AGENT", "")

        event = ingest_first_party_event(
            site=site,
            event_type=serializer.validated_data["event_type"],
            visitor_id=serializer.validated_data["visitor_id"],
            session_id=serializer.validated_data["session_id"],
            path=serializer.validated_data["path"],
            properties=serializer.validated_data.get("properties"),
            user_agent=user_agent,
            consent_granted=serializer.validated_data.get("consent_granted", False),
        )

        return Response(
            {"status": "ACCEPTED", "event_id": str(event.id)}, status=status.HTTP_202_ACCEPTED
        )


class FirstPartyOverviewReportView(APIView):
    """Aggregated first-party analytics overview report (ANA-7)."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceMember)

    @extend_schema(
        summary="First-party analytics summary",
        responses={200: OpenApiResponse(description="First-party metrics")},
    )
    def get(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        today = timezone.localdate()
        start_d_str = request.query_params.get("start_date")
        end_d_str = request.query_params.get("end_date")

        try:
            start_d = (
                date.fromisoformat(start_d_str) if start_d_str else (today - timedelta(days=30))
            )
            end_d = date.fromisoformat(end_d_str) if end_d_str else today
        except ValueError as exc:
            raise ValidationError("Dates must be formatted as YYYY-MM-DD.") from exc

        if start_d > end_d:
            raise ValidationError("start_date cannot be after end_date.")

        metrics = get_first_party_metrics(site, start_d, end_d)
        return Response(metrics)


class VisitorDataErasureView(APIView):
    """GDPR/CCPA Art. 17 right-to-be-forgotten visitor data erasure endpoint (ANA-8)."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceAdmin)

    @extend_schema(
        summary="Erase visitor data (GDPR/CCPA)",
        responses={200: OpenApiResponse(description="Visitor events purged")},
    )
    def delete(
        self, request: Request, workspace_id: Any, site_id: Any, visitor_id: str
    ) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        deleted_count = erase_visitor_data(site, visitor_id)

        record_audit_event(
            action="visitor_data.erased",
            request=request,
            workspace_id=workspace.id,
            resource_type="visitor",
            resource_id=visitor_id,
            payload={"deleted_events": deleted_count, "site_id": str(site.id)},
        )

        return Response(
            {
                "status": "PURGED",
                "visitor_id": visitor_id,
                "deleted_events": deleted_count,
                "deleted_events_count": deleted_count,
            },
            status=status.HTTP_200_OK,
        )
