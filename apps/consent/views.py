"""API views for consent management, public banner contracts, and visitor consent decisions."""

from __future__ import annotations

import logging
from typing import Any

from django.http import Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit_event
from apps.common.pagination import DefaultPagination
from apps.consent.models import (
    PrivacyPolicyVersion,
)
from apps.consent.serializers import (
    ConsentRecordSerializer,
    ConsentSummarySerializer,
    PrivacyPolicyVersionCreateSerializer,
    PrivacyPolicyVersionSerializer,
    PublicBannerConfigSerializer,
    PublicConsentStatusSerializer,
    PublicConsentSubmitSerializer,
    PublicConsentWithdrawSerializer,
    SiteConsentConfigSerializer,
)
from apps.consent.services import (
    export_visitor_consent_history,
    get_consent_summary,
    get_or_create_site_consent_config,
    get_visitor_consent_status,
    purge_visitor_consent_history,
    record_visitor_consent,
    withdraw_visitor_consent,
)
from apps.content.views import _check_public_origin_allowlist
from apps.sites.models import Site
from apps.sites.views import _get_site
from apps.tenancy.permissions import (
    IsWorkspaceAdmin,
    IsWorkspaceMember,
    resolve_workspace,
)

logger = logging.getLogger(__name__)


class SiteConsentConfigView(APIView):
    """Manage per-site cookie consent policies and category rules (CON-1)."""

    def get_permissions(self) -> list[Any]:
        if self.request.method == "GET":
            return [permissions.IsAuthenticated(), IsWorkspaceMember()]
        return [permissions.IsAuthenticated(), IsWorkspaceAdmin()]

    @extend_schema(
        summary="Get site consent configuration",
        responses={200: SiteConsentConfigSerializer},
    )
    def get(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)
        config = get_or_create_site_consent_config(site)
        serializer = SiteConsentConfigSerializer(config)
        return Response(serializer.data)

    @extend_schema(
        summary="Update site consent configuration",
        request=SiteConsentConfigSerializer,
        responses={200: SiteConsentConfigSerializer},
    )
    def patch(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)
        config = get_or_create_site_consent_config(site)

        serializer = SiteConsentConfigSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_config = serializer.save()

        record_audit_event(
            action="consent.config_updated",
            workspace_id=workspace.id,
            resource_type="SiteConsentConfig",
            resource_id=str(updated_config.id),
            actor=request.user if request.user.is_authenticated else None,
            payload={
                "site_id": str(site.id),
                "is_enabled": updated_config.is_enabled,
                "jurisdiction_mode": updated_config.jurisdiction_mode,
                "retention_days": updated_config.retention_days,
            },
        )
        return Response(serializer.data)


class PrivacyPolicyVersionListView(APIView):
    """List and create privacy policy versions for a site (CON-1, CON-4)."""

    def get_permissions(self) -> list[Any]:
        if self.request.method == "GET":
            return [permissions.IsAuthenticated(), IsWorkspaceMember()]
        return [permissions.IsAuthenticated(), IsWorkspaceAdmin()]

    @extend_schema(
        summary="List site privacy policy versions",
        responses={200: PrivacyPolicyVersionSerializer(many=True)},
    )
    def get(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)
        versions = site.privacy_policies.all().order_by("-effective_date", "-created_at")
        serializer = PrivacyPolicyVersionSerializer(versions, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Create privacy policy version",
        request=PrivacyPolicyVersionCreateSerializer,
        responses={201: PrivacyPolicyVersionSerializer},
    )
    def post(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        serializer = PrivacyPolicyVersionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        activate_now = serializer.validated_data.pop("activate_now", False)
        version = serializer.validated_data.get("version")
        if site.privacy_policies.filter(version=version).exists():
            raise ValidationError(
                {"version": f"Policy version '{version}' already exists for this site."}
            )

        policy_version = PrivacyPolicyVersion.objects.create(site=site, **serializer.validated_data)
        if activate_now:
            policy_version.activate()
            record_audit_event(
                action="consent.policy_version_activated",
                workspace_id=workspace.id,
                resource_type="PrivacyPolicyVersion",
                resource_id=str(policy_version.id),
                actor=request.user if request.user.is_authenticated else None,
                payload={"site_id": str(site.id), "version": policy_version.version},
            )

        return Response(
            PrivacyPolicyVersionSerializer(policy_version).data,
            status=status.HTTP_201_CREATED,
        )


class PrivacyPolicyVersionDetailView(APIView):
    """Retrieve and update an existing privacy policy version."""

    def get_permissions(self) -> list[Any]:
        if self.request.method == "GET":
            return [permissions.IsAuthenticated(), IsWorkspaceMember()]
        return [permissions.IsAuthenticated(), IsWorkspaceAdmin()]

    @extend_schema(
        summary="Get privacy policy version details",
        responses={200: PrivacyPolicyVersionSerializer},
    )
    def get(self, request: Request, workspace_id: Any, site_id: Any, version_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)
        version = get_object_or_404(site.privacy_policies, id=version_id)
        return Response(PrivacyPolicyVersionSerializer(version).data)

    @extend_schema(
        summary="Update privacy policy version",
        request=PrivacyPolicyVersionSerializer,
        responses={200: PrivacyPolicyVersionSerializer},
    )
    def patch(self, request: Request, workspace_id: Any, site_id: Any, version_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)
        version = get_object_or_404(site.privacy_policies, id=version_id)

        serializer = PrivacyPolicyVersionSerializer(version, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class PrivacyPolicyVersionActivateView(APIView):
    """Activate a privacy policy version as the current governing policy (CON-4)."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceAdmin)

    @extend_schema(
        summary="Activate privacy policy version",
        request=None,
        responses={200: PrivacyPolicyVersionSerializer},
    )
    def post(self, request: Request, workspace_id: Any, site_id: Any, version_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)
        policy_version = get_object_or_404(site.privacy_policies, id=version_id)

        policy_version.activate()

        record_audit_event(
            action="consent.policy_version_activated",
            workspace_id=workspace.id,
            resource_type="PrivacyPolicyVersion",
            resource_id=str(policy_version.id),
            actor=request.user if request.user.is_authenticated else None,
            payload={"site_id": str(site.id), "version": policy_version.version},
        )
        return Response(PrivacyPolicyVersionSerializer(policy_version).data)


class ConsentRecordListView(APIView):
    """Query paginated consent decision records for compliance audits (CON-6)."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceMember)

    @extend_schema(
        summary="List consent audit records",
        responses={200: ConsentRecordSerializer(many=True)},
    )
    def get(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        qs = site.consent_records.all().order_by("-recorded_at")

        visitor_id = request.query_params.get("visitor_id")
        if visitor_id:
            qs = qs.filter(visitor_id=visitor_id)

        status_param = request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)

        paginator = DefaultPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = ConsentRecordSerializer(page, many=True)
        return paginator.get_paginated_response(list(serializer.data))


class ConsentRecordVisitorPurgeView(APIView):
    """Purge all consent records for a visitor under GDPR Art. 17 right to erasure (CON-6)."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceAdmin)

    @extend_schema(
        summary="Erase visitor consent history (GDPR Art. 17)",
        responses={200: OpenApiResponse(description="Purge summary")},
    )
    def delete(
        self, request: Request, workspace_id: Any, site_id: Any, visitor_id: str
    ) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        actor = request.user if request.user.is_authenticated else None
        deleted_count = purge_visitor_consent_history(site, visitor_id, actor=actor)

        return Response(
            {
                "status": "PURGED",
                "visitor_id": visitor_id,
                "records_deleted": deleted_count,
            }
        )


class ConsentRecordVisitorExportView(APIView):
    """Export complete visitor consent history under GDPR Art. 15/20 portability (CON-6)."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceMember)

    @extend_schema(
        summary="Export visitor consent history (GDPR Art. 15/20)",
        responses={200: OpenApiResponse(description="Visitor consent history export")},
    )
    def get(self, request: Request, workspace_id: Any, site_id: Any, visitor_id: str) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        history = export_visitor_consent_history(site, visitor_id)
        return Response(
            {
                "site": site.slug,
                "visitor_id": visitor_id,
                "records": history,
            }
        )


class ConsentSummaryView(APIView):
    """Retrieve aggregated, anonymous consent statistics (opt-in rates, distributions)."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceMember)

    @extend_schema(
        summary="Get consent summary metrics",
        responses={200: ConsentSummarySerializer},
    )
    def get(self, request: Request, workspace_id: Any, site_id: Any) -> Response:
        workspace = resolve_workspace(request, workspace_id)
        site = _get_site(workspace, site_id)

        summary = get_consent_summary(site)
        serializer = ConsentSummarySerializer(summary)
        return Response(serializer.data)


# ==============================================================================
# Public Browser / SDK Endpoints (Protected by CT-6 Origin Check)
# ==============================================================================


class PublicBannerConfigView(APIView):
    """Public browser contract returning active consent rules and category definitions (CON-2)."""

    permission_classes = (permissions.AllowAny,)

    @extend_schema(
        summary="Get public consent banner configuration",
        responses={
            200: PublicBannerConfigSerializer,
            404: OpenApiResponse(description="Site not found"),
        },
    )
    def get(self, request: Request, site_slug: str) -> Response:
        site = Site.objects.filter(slug=site_slug, is_active=True).first()
        if not site:
            raise Http404("Site not found.")

        _check_public_origin_allowlist(request, site)

        config = get_or_create_site_consent_config(site)
        active_policy = config.active_policy_version
        active_policy_data = None
        if active_policy:
            active_policy_data = {
                "id": str(active_policy.id),
                "version": active_policy.version,
                "title": active_policy.title,
                "summary": active_policy.summary,
                "body": active_policy.body,
                "effective_date": active_policy.effective_date.isoformat(),
            }

        data = {
            "is_enabled": config.is_enabled,
            "jurisdiction_mode": config.jurisdiction_mode,
            "cookie_domain": config.cookie_domain,
            "active_policy": active_policy_data,
            "categories": config.get_all_categories(),
            "default_states": config.get_default_category_states(),
            "gcm_enabled": config.gcm_enabled,
            "gcm_defaults": config.get_gcm_defaults(),
        }
        serializer = PublicBannerConfigSerializer(data)
        return Response(serializer.data)


class PublicConsentSubmitView(APIView):
    """Public endpoint for visitors recording their consent decision (CON-3, CON-5)."""

    permission_classes = (permissions.AllowAny,)

    @extend_schema(
        summary="Submit visitor consent decision",
        request=PublicConsentSubmitSerializer,
        responses={
            201: OpenApiResponse(description="Consent recorded"),
            400: OpenApiResponse(description="Invalid category payload or format"),
            404: OpenApiResponse(description="Site not found"),
        },
    )
    def post(self, request: Request, site_slug: str) -> Response:
        site = Site.objects.filter(slug=site_slug, is_active=True).first()
        if not site:
            raise Http404("Site not found.")

        _check_public_origin_allowlist(request, site)

        serializer = PublicConsentSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        record = record_visitor_consent(
            site=site,
            visitor_id=serializer.validated_data["visitor_id"],
            categories=serializer.validated_data["categories"],
            policy_version_str=serializer.validated_data.get("policy_version") or None,
            consent_type=serializer.validated_data.get("consent_type"),
        )

        # Build GCM update state if enabled
        config = get_or_create_site_consent_config(site)
        gcm_update: dict[str, str] = {}
        if config.gcm_enabled:
            analytics_granted = record.categories.get("analytics", False)
            marketing_granted = record.categories.get("marketing", False)
            gcm_update = {
                "analytics_storage": "granted" if analytics_granted else "denied",
                "ad_storage": "granted" if marketing_granted else "denied",
                "ad_user_data": "granted" if marketing_granted else "denied",
                "ad_personalization": "granted" if marketing_granted else "denied",
            }

        return Response(
            {
                "status": "RECORDED",
                "record_id": str(record.id),
                "decision_status": record.status,
                "categories": record.categories,
                "gcm_update": gcm_update,
            },
            status=status.HTTP_201_CREATED,
        )


class PublicConsentWithdrawView(APIView):
    """Public endpoint for visitors withdrawing consent (CON-4)."""

    permission_classes = (permissions.AllowAny,)

    @extend_schema(
        summary="Withdraw visitor consent",
        request=PublicConsentWithdrawSerializer,
        responses={
            200: OpenApiResponse(description="Consent withdrawn"),
            404: OpenApiResponse(description="Site not found"),
        },
    )
    def post(self, request: Request, site_slug: str) -> Response:
        site = Site.objects.filter(slug=site_slug, is_active=True).first()
        if not site:
            raise Http404("Site not found.")

        _check_public_origin_allowlist(request, site)

        serializer = PublicConsentWithdrawSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        record = withdraw_visitor_consent(
            site=site,
            visitor_id=serializer.validated_data["visitor_id"],
        )

        # If GCM enabled, all optional signals reset to denied
        config = get_or_create_site_consent_config(site)
        gcm_update: dict[str, str] = {}
        if config.gcm_enabled:
            gcm_update = {
                "analytics_storage": "denied",
                "ad_storage": "denied",
                "ad_user_data": "denied",
                "ad_personalization": "denied",
            }

        return Response(
            {
                "status": "WITHDRAWN",
                "record_id": str(record.id),
                "categories": record.categories,
                "gcm_update": gcm_update,
            },
            status=status.HTTP_200_OK,
        )


class PublicConsentStatusView(APIView):
    """Public endpoint for checking effective visitor consent status (CON-2, CON-4)."""

    permission_classes = (permissions.AllowAny,)

    @extend_schema(
        summary="Query visitor consent status",
        responses={
            200: PublicConsentStatusSerializer,
            404: OpenApiResponse(description="Site not found"),
        },
    )
    def get(self, request: Request, site_slug: str) -> Response:
        site = Site.objects.filter(slug=site_slug, is_active=True).first()
        if not site:
            raise Http404("Site not found.")

        _check_public_origin_allowlist(request, site)

        visitor_id = request.query_params.get("visitor_id")
        if not visitor_id:
            raise ValidationError({"visitor_id": "visitor_id query parameter is required."})

        consent_status = get_visitor_consent_status(site, visitor_id)
        serializer = PublicConsentStatusSerializer(consent_status)
        return Response(serializer.data)
