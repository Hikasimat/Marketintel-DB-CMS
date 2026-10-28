"""Views for analytics configuration, GA4 reports, ingestion, and metrics."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from django.http import Http404
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analytics.adapters.ga4 import GA4ReportingAdapter
from apps.analytics.models import (
    AnalyticsReportSnapshot,
    GA4Connection,
    SiteAnalyticsConfig,
)
from apps.analytics.serializers import (
    EventIngestSerializer,
    GA4ConnectionSerializer,
    GA4ReportRequestSerializer,
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

        # Check cached snapshot
        if use_cache:
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

        if report_type == "traffic_sources":
            report_data = adapter.get_traffic_sources(start_str, end_str)
        elif report_type == "top_pages":
            report_data = adapter.get_top_pages(start_str, end_str)
        else:
            report_data = adapter.get_overview(start_str, end_str)

        if report_data.get("status") == "SUCCESS":
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
            properties=serializer.validated_data.get("properties", {}),
            user_agent=user_agent,
            consent_granted=serializer.validated_data.get("consent_granted", False),
        )

        return Response(
            {"status": "ACCEPTED", "event_id": str(event.id)},
            status=status.HTTP_202_ACCEPTED,
        )


class FirstPartyOverviewReportView(APIView):
    """Retrieve aggregated first-party analytics metrics and time-series (ANA-7)."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceMember)

    @extend_schema(
        summary="Get first-party analytics overview",
        responses={200: OpenApiResponse(description="Aggregated metrics summary")},
    )
    def get(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        today = timezone.localdate()
        start_param = request.query_params.get("start_date")
        end_param = request.query_params.get("end_date")

        try:
            start_d = (
                date.fromisoformat(start_param) if start_param else (today - timedelta(days=30))
            )
            end_d = date.fromisoformat(end_param) if end_param else today
        except ValueError as exc:
            raise ValidationError("Invalid date format. Expected YYYY-MM-DD.") from exc

        if start_d > end_d:
            raise ValidationError("start_date cannot be after end_date.")

        metrics = get_first_party_metrics(site, start_d, end_d)
        return Response(metrics)


class VisitorDataErasureView(APIView):
    """Erase all event records for a pseudonymous visitor ID (GDPR Art. 17 right to erasure)."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceAdmin)

    @extend_schema(
        summary="Erase visitor analytics events",
        responses={200: OpenApiResponse(description="Erasure result")},
    )
    def delete(
        self, request: Request, workspace_id: Any, site_id: Any, visitor_id: str
    ) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        deleted_count = erase_visitor_data(site, visitor_id)

        record_audit_event(
            action="analytics.visitor_erasure",
            request=request,
            workspace_id=workspace.id,
            resource_type="visitor_data",
            resource_id=visitor_id,
            payload={"deleted_events": deleted_count, "site_id": str(site.id)},
        )

        return Response({"status": "DELETED", "deleted_events": deleted_count})
