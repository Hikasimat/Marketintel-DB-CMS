"""API Views for Google Ads OAuth, reporting, mutations, and audit logs."""

from __future__ import annotations

import logging
import os
import urllib.parse
from typing import ClassVar

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.google_ads.adapters.google_ads import GoogleAdsAdapter
from apps.google_ads.models import GoogleAdsCampaignAuditLog, GoogleAdsConnection
from apps.google_ads.serializers import (
    GoogleAdsAuthorizeSerializer,
    GoogleAdsBudgetUpdateSerializer,
    GoogleAdsCallbackSerializer,
    GoogleAdsCampaignActionSerializer,
    GoogleAdsCampaignAuditLogSerializer,
    GoogleAdsConnectionSerializer,
    GoogleAdsCustomerSelectSerializer,
    GoogleAdsDateRangeSerializer,
)
from apps.tenancy.models import Workspace, WorkspaceMembership

logger = logging.getLogger(__name__)

GOOGLE_ADS_SCOPE = "https://www.googleapis.com/auth/adwords"


def _check_workspace_access(request: Request, workspace: Workspace) -> bool:
    user = request.user
    if not isinstance(user, User):
        return False
    if user.is_superuser:
        return True
    return WorkspaceMembership.objects.filter(workspace=workspace, user=user).exists()


def _get_google_ads_adapter(connection: GoogleAdsConnection) -> GoogleAdsAdapter:
    creds = connection.get_credentials()
    access_token = creds.get("access_token") or creds.get("token") or "mock-ads-token"
    dev_token = connection.get_developer_token() or os.getenv(
        "GOOGLE_ADS_DEVELOPER_TOKEN", "mock-developer-token"
    )
    return GoogleAdsAdapter(
        customer_id=connection.customer_id,
        access_token=access_token,
        developer_token=dev_token,
        manager_customer_id=connection.manager_customer_id,
    )


class GoogleAdsConnectionDetailView(APIView):
    permission_classes: ClassVar[list[type[permissions.BasePermission]]] = [
        permissions.IsAuthenticated
    ]

    def get(self, request: Request, workspace_id: str) -> Response:
        workspace = get_object_or_404(Workspace, id=workspace_id)
        if not _check_workspace_access(request, workspace):
            return Response(
                {"detail": "You do not have access to this workspace."},
                status=status.HTTP_403_FORBIDDEN,
            )
        connection = GoogleAdsConnection.objects.filter(workspace=workspace).first()
        if not connection:
            return Response({"connected": False, "connection": None})
        serializer = GoogleAdsConnectionSerializer(connection)
        return Response({"connected": connection.is_active, "connection": serializer.data})


class GoogleAdsAuthorizeView(APIView):
    permission_classes: ClassVar[list[type[permissions.BasePermission]]] = [
        permissions.IsAuthenticated
    ]

    def get(self, request: Request, workspace_id: str) -> Response:
        workspace = get_object_or_404(Workspace, id=workspace_id)
        if not _check_workspace_access(request, workspace):
            return Response(
                {"detail": "You do not have access to this workspace."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = GoogleAdsAuthorizeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        client_id = getattr(
            settings,
            "GOOGLE_ADS_CLIENT_ID",
            getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", ""),
        ) or os.getenv("GOOGLE_OAUTH_CLIENT_ID", "mock-client-id")

        redirect_uri = serializer.validated_data.get("redirect_uri") or (
            request.build_absolute_uri(f"/api/v1/workspaces/{workspace.id}/google-ads/callback/")
        )

        state = f"ws:{workspace.id}"
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": GOOGLE_ADS_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
        return Response({"authorization_url": auth_url, "state": state})


class GoogleAdsCallbackView(APIView):
    permission_classes: ClassVar[list[type[permissions.BasePermission]]] = [
        permissions.IsAuthenticated
    ]

    def post(self, request: Request, workspace_id: str) -> Response:
        workspace = get_object_or_404(Workspace, id=workspace_id)
        if not _check_workspace_access(request, workspace):
            return Response(
                {"detail": "You do not have access to this workspace."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = GoogleAdsCallbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        code = serializer.validated_data["code"]
        redirect_uri = serializer.validated_data["redirect_uri"]
        developer_token = serializer.validated_data.get("developer_token", "")

        is_test = getattr(settings, "SETTINGS_PROFILE", "") == "test" or os.getenv(
            "DJANGO_SETTINGS_MODULE", ""
        ).endswith(".test")

        if is_test or code.startswith("mock-"):
            tokens = {
                "access_token": f"mock-token-{code}",
                "refresh_token": "mock-refresh-token",
                "token_type": "Bearer",
                "expires_in": 3600,
            }
        else:
            client_id = getattr(
                settings,
                "GOOGLE_ADS_CLIENT_ID",
                getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", ""),
            ) or os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
            client_secret = getattr(
                settings,
                "GOOGLE_ADS_CLIENT_SECRET",
                getattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", ""),
            ) or os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")

            import requests

            token_url = "https://oauth2.googleapis.com/token"  # noqa: S105
            data = {
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            }
            try:
                resp = requests.post(token_url, data=data, timeout=10)
                if resp.status_code != 200:
                    return Response(
                        {
                            "error": "Failed to exchange authorization code with Google.",
                            "details": resp.text,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                tokens = resp.json()
            except Exception as exc:
                return Response(
                    {"error": f"Token exchange failed: {exc}"},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

        connection, _ = GoogleAdsConnection.objects.get_or_create(workspace=workspace)
        connection.set_credentials(tokens)
        if developer_token:
            connection.set_developer_token(developer_token)
        connection.is_active = True
        connection.status = "CONNECTED"
        connection.last_synced_at = timezone.now()
        connection.last_error = ""
        connection.save()

        return Response(
            {
                "status": "connected",
                "message": "Google Ads authorization completed.",
                "connection": GoogleAdsConnectionSerializer(connection).data,
            }
        )


class GoogleAdsDisconnectView(APIView):
    permission_classes: ClassVar[list[type[permissions.BasePermission]]] = [
        permissions.IsAuthenticated
    ]

    def post(self, request: Request, workspace_id: str) -> Response:
        workspace = get_object_or_404(Workspace, id=workspace_id)
        if not _check_workspace_access(request, workspace):
            return Response(
                {"detail": "You do not have access to this workspace."},
                status=status.HTTP_403_FORBIDDEN,
            )

        connection = GoogleAdsConnection.objects.filter(workspace=workspace).first()
        if connection:
            connection.set_credentials({})
            connection.is_active = False
            connection.status = "DISCONNECTED"
            connection.customer_id = ""
            connection.save()

        return Response({"status": "disconnected", "message": "Google Ads connection severed."})


class GoogleAdsCustomerListView(APIView):
    permission_classes: ClassVar[list[type[permissions.BasePermission]]] = [
        permissions.IsAuthenticated
    ]

    def get(self, request: Request, workspace_id: str) -> Response:
        workspace = get_object_or_404(Workspace, id=workspace_id)
        if not _check_workspace_access(request, workspace):
            return Response(
                {"detail": "You do not have access to this workspace."},
                status=status.HTTP_403_FORBIDDEN,
            )

        connection = GoogleAdsConnection.objects.filter(workspace=workspace, is_active=True).first()
        if not connection or not connection.encrypted_credentials:
            return Response(
                {"error": "No active Google Ads connection found for this workspace."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        adapter = _get_google_ads_adapter(connection)
        customers = adapter.list_accessible_customers()
        clean_ids = [c.replace("customers/", "") for c in customers]
        return Response({"customers": clean_ids, "count": len(clean_ids)})


class GoogleAdsCustomerSelectView(APIView):
    permission_classes: ClassVar[list[type[permissions.BasePermission]]] = [
        permissions.IsAuthenticated
    ]

    def post(self, request: Request, workspace_id: str) -> Response:
        workspace = get_object_or_404(Workspace, id=workspace_id)
        if not _check_workspace_access(request, workspace):
            return Response(
                {"detail": "You do not have access to this workspace."},
                status=status.HTTP_403_FORBIDDEN,
            )

        connection = GoogleAdsConnection.objects.filter(workspace=workspace, is_active=True).first()
        if not connection:
            return Response(
                {"error": "No active Google Ads connection found for this workspace."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = GoogleAdsCustomerSelectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        customer_id = serializer.validated_data["customer_id"].replace("-", "").strip()
        manager_id = (
            serializer.validated_data.get("manager_customer_id", "").replace("-", "").strip()
        )
        dev_token = serializer.validated_data.get("developer_token", "").strip()

        connection.customer_id = customer_id
        if manager_id:
            connection.manager_customer_id = manager_id
        if dev_token:
            connection.set_developer_token(dev_token)
        connection.save()

        return Response(
            {
                "status": "selected",
                "customer_id": customer_id,
                "manager_customer_id": connection.manager_customer_id,
                "connection": GoogleAdsConnectionSerializer(connection).data,
            }
        )


class GoogleAdsCampaignsView(APIView):
    permission_classes: ClassVar[list[type[permissions.BasePermission]]] = [
        permissions.IsAuthenticated
    ]

    def get(self, request: Request, workspace_id: str) -> Response:
        workspace = get_object_or_404(Workspace, id=workspace_id)
        if not _check_workspace_access(request, workspace):
            return Response(
                {"detail": "You do not have access to this workspace."},
                status=status.HTTP_403_FORBIDDEN,
            )

        connection = GoogleAdsConnection.objects.filter(workspace=workspace, is_active=True).first()
        if not connection or not connection.customer_id:
            return Response(
                {"error": "Google Ads connection not configured with a customer ID."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = GoogleAdsDateRangeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        start_date = str(serializer.validated_data["start_date"])
        end_date = str(serializer.validated_data["end_date"])

        adapter = _get_google_ads_adapter(connection)
        campaigns = adapter.get_campaigns(start_date, end_date)
        return Response(
            {
                "customer_id": connection.customer_id,
                "start_date": start_date,
                "end_date": end_date,
                "campaigns": campaigns,
                "count": len(campaigns),
            }
        )


class GoogleAdsAdGroupsView(APIView):
    permission_classes: ClassVar[list[type[permissions.BasePermission]]] = [
        permissions.IsAuthenticated
    ]

    def get(self, request: Request, workspace_id: str) -> Response:
        workspace = get_object_or_404(Workspace, id=workspace_id)
        if not _check_workspace_access(request, workspace):
            return Response(
                {"detail": "You do not have access to this workspace."},
                status=status.HTTP_403_FORBIDDEN,
            )

        connection = GoogleAdsConnection.objects.filter(workspace=workspace, is_active=True).first()
        if not connection or not connection.customer_id:
            return Response(
                {"error": "Google Ads connection not configured with a customer ID."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = GoogleAdsDateRangeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        start_date = str(serializer.validated_data["start_date"])
        end_date = str(serializer.validated_data["end_date"])

        adapter = _get_google_ads_adapter(connection)
        ad_groups = adapter.get_ad_groups(start_date, end_date)
        return Response(
            {
                "customer_id": connection.customer_id,
                "start_date": start_date,
                "end_date": end_date,
                "ad_groups": ad_groups,
                "count": len(ad_groups),
            }
        )


class GoogleAdsKeywordsView(APIView):
    permission_classes: ClassVar[list[type[permissions.BasePermission]]] = [
        permissions.IsAuthenticated
    ]

    def get(self, request: Request, workspace_id: str) -> Response:
        workspace = get_object_or_404(Workspace, id=workspace_id)
        if not _check_workspace_access(request, workspace):
            return Response(
                {"detail": "You do not have access to this workspace."},
                status=status.HTTP_403_FORBIDDEN,
            )

        connection = GoogleAdsConnection.objects.filter(workspace=workspace, is_active=True).first()
        if not connection or not connection.customer_id:
            return Response(
                {"error": "Google Ads connection not configured with a customer ID."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = GoogleAdsDateRangeSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        start_date = str(serializer.validated_data["start_date"])
        end_date = str(serializer.validated_data["end_date"])

        adapter = _get_google_ads_adapter(connection)
        keywords = adapter.get_keywords(start_date, end_date)
        return Response(
            {
                "customer_id": connection.customer_id,
                "start_date": start_date,
                "end_date": end_date,
                "keywords": keywords,
                "count": len(keywords),
            }
        )


class GoogleAdsCampaignPauseView(APIView):
    permission_classes: ClassVar[list[type[permissions.BasePermission]]] = [
        permissions.IsAuthenticated
    ]

    def post(self, request: Request, workspace_id: str, campaign_id: str) -> Response:
        workspace = get_object_or_404(Workspace, id=workspace_id)
        if not _check_workspace_access(request, workspace):
            return Response(
                {"detail": "You do not have access to this workspace."},
                status=status.HTTP_403_FORBIDDEN,
            )

        connection = GoogleAdsConnection.objects.filter(workspace=workspace, is_active=True).first()
        if not connection or not connection.customer_id:
            return Response(
                {"error": "Google Ads connection not configured with a customer ID."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = GoogleAdsCampaignActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        campaign_name = serializer.validated_data.get("campaign_name", "")
        adapter = _get_google_ads_adapter(connection)
        result = adapter.set_campaign_status(campaign_id=campaign_id, new_status="PAUSED")

        user = request.user if isinstance(request.user, User) else None
        audit_log = GoogleAdsCampaignAuditLog.objects.create(
            connection=connection,
            action=GoogleAdsCampaignAuditLog.Action.CAMPAIGN_PAUSE,
            campaign_id=campaign_id,
            campaign_name=campaign_name,
            performed_by=user,
            details={"result": result},
        )

        return Response(
            {
                "status": "PAUSED",
                "campaign_id": campaign_id,
                "audit_log_id": str(audit_log.id),
                "result": result,
            }
        )


class GoogleAdsCampaignResumeView(APIView):
    permission_classes: ClassVar[list[type[permissions.BasePermission]]] = [
        permissions.IsAuthenticated
    ]

    def post(self, request: Request, workspace_id: str, campaign_id: str) -> Response:
        workspace = get_object_or_404(Workspace, id=workspace_id)
        if not _check_workspace_access(request, workspace):
            return Response(
                {"detail": "You do not have access to this workspace."},
                status=status.HTTP_403_FORBIDDEN,
            )

        connection = GoogleAdsConnection.objects.filter(workspace=workspace, is_active=True).first()
        if not connection or not connection.customer_id:
            return Response(
                {"error": "Google Ads connection not configured with a customer ID."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = GoogleAdsCampaignActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        campaign_name = serializer.validated_data.get("campaign_name", "")
        adapter = _get_google_ads_adapter(connection)
        result = adapter.set_campaign_status(campaign_id=campaign_id, new_status="ENABLED")

        user = request.user if isinstance(request.user, User) else None
        audit_log = GoogleAdsCampaignAuditLog.objects.create(
            connection=connection,
            action=GoogleAdsCampaignAuditLog.Action.CAMPAIGN_RESUME,
            campaign_id=campaign_id,
            campaign_name=campaign_name,
            performed_by=user,
            details={"result": result},
        )

        return Response(
            {
                "status": "ENABLED",
                "campaign_id": campaign_id,
                "audit_log_id": str(audit_log.id),
                "result": result,
            }
        )


class GoogleAdsCampaignBudgetView(APIView):
    permission_classes: ClassVar[list[type[permissions.BasePermission]]] = [
        permissions.IsAuthenticated
    ]

    def post(self, request: Request, workspace_id: str, campaign_id: str) -> Response:
        workspace = get_object_or_404(Workspace, id=workspace_id)
        if not _check_workspace_access(request, workspace):
            return Response(
                {"detail": "You do not have access to this workspace."},
                status=status.HTTP_403_FORBIDDEN,
            )

        connection = GoogleAdsConnection.objects.filter(workspace=workspace, is_active=True).first()
        if not connection or not connection.customer_id:
            return Response(
                {"error": "Google Ads connection not configured with a customer ID."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        data.setdefault("campaign_id", campaign_id)
        serializer = GoogleAdsBudgetUpdateSerializer(data=data)
        serializer.is_valid(raise_exception=True)

        budget_resource_name = serializer.validated_data["budget_resource_name"]
        amount_micros = serializer.validated_data["amount_micros"]
        campaign_name = serializer.validated_data.get("campaign_name", "")

        adapter = _get_google_ads_adapter(connection)
        result = adapter.update_campaign_budget(
            budget_resource_name=budget_resource_name,
            amount_micros=amount_micros,
        )

        user = request.user if isinstance(request.user, User) else None
        audit_log = GoogleAdsCampaignAuditLog.objects.create(
            connection=connection,
            action=GoogleAdsCampaignAuditLog.Action.BUDGET_UPDATE,
            campaign_id=campaign_id,
            campaign_name=campaign_name,
            performed_by=user,
            details={
                "budget_resource_name": budget_resource_name,
                "amount_micros": amount_micros,
                "result": result,
            },
        )

        return Response(
            {
                "status": "UPDATED",
                "campaign_id": campaign_id,
                "amount_micros": amount_micros,
                "audit_log_id": str(audit_log.id),
                "result": result,
            }
        )


class GoogleAdsAuditLogListView(APIView):
    permission_classes: ClassVar[list[type[permissions.BasePermission]]] = [
        permissions.IsAuthenticated
    ]

    def get(self, request: Request, workspace_id: str) -> Response:
        workspace = get_object_or_404(Workspace, id=workspace_id)
        if not _check_workspace_access(request, workspace):
            return Response(
                {"detail": "You do not have access to this workspace."},
                status=status.HTTP_403_FORBIDDEN,
            )

        connection = GoogleAdsConnection.objects.filter(workspace=workspace).first()
        if not connection:
            return Response({"audit_logs": [], "count": 0})

        logs = connection.audit_logs.select_related("performed_by").all()[:100]
        serializer = GoogleAdsCampaignAuditLogSerializer(logs, many=True)
        return Response({"audit_logs": serializer.data, "count": len(serializer.data)})
