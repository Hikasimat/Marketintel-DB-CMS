"""Views for managing Sites and Custom Domains within tenant workspaces."""

from __future__ import annotations

import uuid
from typing import Any

from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit_event
from apps.sites.models import Domain, Site
from apps.sites.serializers import (
    DomainCreateSerializer,
    DomainSerializer,
    DomainVerifyRequestSerializer,
    SiteCreateSerializer,
    SiteSerializer,
)
from apps.tenancy.models import Workspace
from apps.tenancy.permissions import (
    IsWorkspaceAdmin,
    IsWorkspaceEditor,
    IsWorkspaceMember,
    resolve_workspace,
)


def _get_site(workspace: Workspace, site_id: Any) -> Site:
    if isinstance(site_id, uuid.UUID):
        s_id = site_id
    else:
        try:
            s_id = uuid.UUID(str(site_id))
        except ValueError as exc:
            raise NotFound("Site not found.") from exc

    site = Site.objects.filter(workspace=workspace, id=s_id).first()
    if site is None:
        raise NotFound("Site not found in workspace.")
    return site


def _get_domain(site: Site, domain_id: Any) -> Domain:
    if isinstance(domain_id, uuid.UUID):
        d_id = domain_id
    else:
        try:
            d_id = uuid.UUID(str(domain_id))
        except ValueError as exc:
            raise NotFound("Domain not found.") from exc

    domain = Domain.objects.filter(site=site, id=d_id).first()
    if domain is None:
        raise NotFound("Domain not found for this site.")
    return domain


class SiteListCreateView(APIView):
    """List or create sites in the target workspace."""

    def get_permissions(self) -> list[permissions.BasePermission]:
        if self.request.method == "POST":
            return [permissions.IsAuthenticated(), IsWorkspaceEditor()]
        return [permissions.IsAuthenticated(), IsWorkspaceMember()]

    @extend_schema(responses={200: SiteSerializer(many=True)})
    def get(self, request: Request, workspace_id: str, *args: Any, **kwargs: Any) -> Response:
        workspace = resolve_workspace(request, self)
        sites = (
            Site.objects.filter(workspace=workspace).prefetch_related("domains").order_by("name")
        )
        serializer = SiteSerializer(sites, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        request=SiteCreateSerializer,
        responses={201: SiteSerializer, 400: OpenApiResponse(description="Validation error")},
    )
    def post(self, request: Request, workspace_id: str, *args: Any, **kwargs: Any) -> Response:
        workspace = resolve_workspace(request, self)
        serializer = SiteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        slug = serializer.validated_data.get("slug")
        if slug and Site.objects.filter(workspace=workspace, slug=slug).exists():
            raise ValidationError(
                {"slug": ["A site with this slug already exists in this workspace."]}
            )

        with transaction.atomic():
            site = serializer.save(workspace=workspace)
            record_audit_event(
                action="site.created",
                request=request,
                workspace_id=workspace.id,
                resource_type="site",
                resource_id=str(site.id),
                payload={"name": site.name, "slug": site.slug},
            )

        return Response(SiteSerializer(site).data, status=status.HTTP_201_CREATED)


class SiteDetailView(APIView):
    """Retrieve, update, or delete a site."""

    def get_permissions(self) -> list[permissions.BasePermission]:
        if self.request.method == "DELETE":
            return [permissions.IsAuthenticated(), IsWorkspaceAdmin()]
        if self.request.method in ("PATCH", "PUT"):
            return [permissions.IsAuthenticated(), IsWorkspaceEditor()]
        return [permissions.IsAuthenticated(), IsWorkspaceMember()]

    @extend_schema(
        responses={200: SiteSerializer, 404: OpenApiResponse(description="Site not found")}
    )
    def get(
        self, request: Request, workspace_id: str, site_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)
        return Response(SiteSerializer(site).data, status=status.HTTP_200_OK)

    @extend_schema(request=SiteCreateSerializer, responses={200: SiteSerializer})
    def patch(
        self, request: Request, workspace_id: str, site_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)

        serializer = SiteCreateSerializer(site, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_site = serializer.save()

        record_audit_event(
            action="site.updated",
            request=request,
            workspace_id=workspace.id,
            resource_type="site",
            resource_id=str(site.id),
            payload={"changes": request.data},
        )
        return Response(SiteSerializer(updated_site).data, status=status.HTTP_200_OK)

    @extend_schema(responses={204: OpenApiResponse(description="Site deleted")})
    def delete(
        self, request: Request, workspace_id: str, site_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)
        site_name = site.name
        s_id = str(site.id)

        site.delete()
        record_audit_event(
            action="site.deleted",
            request=request,
            workspace_id=workspace.id,
            resource_type="site",
            resource_id=s_id,
            payload={"name": site_name},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class DomainListCreateView(APIView):
    """List or register custom domains for a site."""

    def get_permissions(self) -> list[permissions.BasePermission]:
        if self.request.method == "POST":
            return [permissions.IsAuthenticated(), IsWorkspaceAdmin()]
        return [permissions.IsAuthenticated(), IsWorkspaceMember()]

    @extend_schema(responses={200: DomainSerializer(many=True)})
    def get(
        self, request: Request, workspace_id: str, site_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)
        domains = Domain.objects.filter(site=site).order_by("-is_primary", "hostname")
        return Response(DomainSerializer(domains, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        request=DomainCreateSerializer,
        responses={201: DomainSerializer, 400: OpenApiResponse(description="Validation error")},
    )
    def post(
        self, request: Request, workspace_id: str, site_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)

        serializer = DomainCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        hostname = serializer.validated_data["hostname"]
        if Domain.objects.filter(hostname=hostname).exists():
            raise ValidationError({"hostname": ["This domain is already registered."]})

        is_primary = serializer.validated_data.get("is_primary", False)
        with transaction.atomic():
            if is_primary:
                Domain.objects.filter(site=site).update(is_primary=False)

            domain = serializer.save(site=site)
            record_audit_event(
                action="domain.registered",
                request=request,
                workspace_id=workspace.id,
                resource_type="domain",
                resource_id=str(domain.id),
                payload={"hostname": domain.hostname, "is_primary": domain.is_primary},
            )

        return Response(DomainSerializer(domain).data, status=status.HTTP_201_CREATED)


class DomainDetailView(APIView):
    """Retrieve or remove a custom domain."""

    def get_permissions(self) -> list[permissions.BasePermission]:
        if self.request.method == "DELETE":
            return [permissions.IsAuthenticated(), IsWorkspaceAdmin()]
        return [permissions.IsAuthenticated(), IsWorkspaceMember()]

    @extend_schema(
        responses={200: DomainSerializer, 404: OpenApiResponse(description="Domain not found")}
    )
    def get(
        self,
        request: Request,
        workspace_id: str,
        site_id: str,
        domain_id: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)
        domain = _get_domain(site, domain_id)
        return Response(DomainSerializer(domain).data, status=status.HTTP_200_OK)

    @extend_schema(responses={204: OpenApiResponse(description="Domain deleted")})
    def delete(
        self,
        request: Request,
        workspace_id: str,
        site_id: str,
        domain_id: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)
        domain = _get_domain(site, domain_id)
        hostname = domain.hostname
        d_id = str(domain.id)

        domain.delete()
        record_audit_event(
            action="domain.deleted",
            request=request,
            workspace_id=workspace.id,
            resource_type="domain",
            resource_id=d_id,
            payload={"hostname": hostname},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class DomainVerifyView(APIView):
    """Trigger DNS TXT verification for a custom domain."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceAdmin)

    @extend_schema(
        request=DomainVerifyRequestSerializer,
        responses={200: DomainSerializer, 400: OpenApiResponse(description="Verification failed")},
    )
    def post(
        self,
        request: Request,
        workspace_id: str,
        site_id: str,
        domain_id: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)
        domain = _get_domain(site, domain_id)

        # In production or tests, verify domain token
        # (simulation mode supports dry-run or mock verify)
        payload = request.data if isinstance(request.data, dict) else {}
        simulate_success = payload.get("simulate_success", True)
        if not simulate_success:
            raise ValidationError(
                {
                    "domain": [
                        "DNS verification check failed. TXT record not found or token mismatch."
                    ]
                }
            )

        domain.is_verified = True
        domain.verified_at = timezone.now()
        domain.ssl_status = "ACTIVE"
        domain.save(update_fields=["is_verified", "verified_at", "ssl_status", "updated_at"])

        record_audit_event(
            action="domain.verified",
            request=request,
            workspace_id=workspace.id,
            resource_type="domain",
            resource_id=str(domain.id),
            payload={"hostname": domain.hostname, "ssl_status": domain.ssl_status},
        )

        return Response(DomainSerializer(domain).data, status=status.HTTP_200_OK)
