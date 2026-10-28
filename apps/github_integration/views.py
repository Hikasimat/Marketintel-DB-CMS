"""Views for GitHub App installations, repository connections, framework analysis, and webhooks."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from typing import Any

from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import (
    NotFound,
    PermissionDenied,
    ValidationError,
)
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_audit_event
from apps.github_integration.analyzer import (
    analyze_repository_manifests,
    generate_integration_patch_files,
)
from apps.github_integration.client import get_github_client
from apps.github_integration.models import (
    GitHubAppInstallation,
    GitHubWebhookDelivery,
    IntegrationStatus,
    SiteGitHubRepoConnection,
)
from apps.github_integration.permissions import IsGitHubAppEnabled
from apps.github_integration.serializers import (
    FrameworkDetectionResponseSerializer,
    GitHubAppInstallationRegisterSerializer,
    GitHubAppInstallationSerializer,
    GitHubRepoConnectSerializer,
    IntegrationPROpenSerializer,
    IntegrationPRResponseSerializer,
    SiteGitHubRepoConnectionSerializer,
)
from apps.sites.models import Site
from apps.tenancy.models import Workspace
from apps.tenancy.permissions import (
    IsWorkspaceAdmin,
    IsWorkspaceMember,
    resolve_workspace,
)

logger = logging.getLogger(__name__)


def _get_site(workspace: Workspace, site_id: Any) -> Site:
    """Resolve site scoped strictly to tenant workspace (preventing IDOR)."""
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


class GitHubWebhookView(APIView):
    """Inbound webhook receiver with HMAC-SHA256 signature and replay defense (GH-6)."""

    permission_classes = (permissions.AllowAny,)
    authentication_classes = ()

    @extend_schema(
        summary="GitHub App Webhook Ingestion",
        description=("Verify HMAC-SHA256 signature, deduplicate delivery ID, and process events."),
        request=None,
        responses={
            200: OpenApiResponse(description="Webhook received and processed."),
            400: OpenApiResponse(description="Missing required webhook headers."),
            401: OpenApiResponse(description="Invalid signature verification."),
            403: OpenApiResponse(description="GitHub App integration disabled."),
        },
        tags=["GitHub Integration"],
    )
    def post(self, request: Request) -> Response:
        # Check feature flag
        if not getattr(settings, "GITHUB_APP_ENABLED", False):
            raise PermissionDenied("GitHub App integration is disabled on this server.")

        # Signature verification (GH-6)
        signature = request.headers.get("X-Hub-Signature-256")
        if not signature:
            logger.warning("GitHub webhook rejected: missing X-Hub-Signature-256 header.")
            return Response(
                {"detail": "Missing X-Hub-Signature-256 header."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        webhook_secret = getattr(settings, "GITHUB_APP_WEBHOOK_SECRET", "")
        if not webhook_secret:
            logger.error("GitHub webhook secret is not configured in settings.")
            return Response(
                {"detail": "GitHub App webhook secret is not configured."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        body = request.body
        expected_sig = (
            "sha256=" + hmac.new(webhook_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        )

        if not hmac.compare_digest(expected_sig, signature):
            logger.warning("GitHub webhook rejected: invalid HMAC-SHA256 signature.")
            return Response(
                {"detail": "Invalid webhook signature."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Replay defense via Delivery ID
        delivery_id = request.headers.get("X-GitHub-Delivery")
        if not delivery_id:
            logger.warning("GitHub webhook rejected: missing X-GitHub-Delivery header.")
            raise ValidationError({"detail": "Missing X-GitHub-Delivery header."})

        if GitHubWebhookDelivery.objects.filter(delivery_id=delivery_id).exists():
            logger.info("GitHub webhook replay detected and dropped: delivery_id=%s", delivery_id)
            return Response(
                {"status": "ignored", "detail": "Replay delivery already processed."},
                status=status.HTTP_200_OK,
            )

        event_type = request.headers.get("X-GitHub-Event", "unknown")

        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except json.JSONDecodeError as exc:
            raise ValidationError({"detail": f"Malformed JSON payload: {exc.msg}"}) from exc

        # Record delivery record for replay protection
        GitHubWebhookDelivery.objects.create(
            delivery_id=delivery_id,
            event_type=event_type,
            status="PROCESSED",
        )

        action = payload.get("action", "")

        # Process lifecycle events
        if event_type == "installation":
            installation_data = payload.get("installation", {})
            inst_id = installation_data.get("id")
            if inst_id:
                inst = GitHubAppInstallation.objects.filter(installation_id=inst_id).first()
                if inst:
                    if action == "deleted":
                        inst.is_active = False
                        inst.save(update_fields=["is_active", "updated_at"])
                        SiteGitHubRepoConnection.objects.filter(installation=inst).update(
                            integration_status=IntegrationStatus.DISCONNECTED,
                            last_error="GitHub App installation uninstalled by customer.",
                        )
                    elif action == "suspend":
                        inst.is_active = False
                        inst.suspended_at = timezone.now()
                        inst.save(update_fields=["is_active", "suspended_at", "updated_at"])
                    elif action == "unsuspend":
                        inst.is_active = True
                        inst.suspended_at = None
                        inst.save(update_fields=["is_active", "suspended_at", "updated_at"])

        elif event_type == "installation_repositories":
            inst_data = payload.get("installation", {})
            inst_id = inst_data.get("id")
            if inst_id and action == "removed":
                repos_removed = [
                    r.get("full_name")
                    for r in payload.get("repositories_removed", [])
                    if r.get("full_name")
                ]
                if repos_removed:
                    SiteGitHubRepoConnection.objects.filter(
                        installation__installation_id=inst_id,
                        repo_full_name__in=repos_removed,
                    ).update(
                        integration_status=IntegrationStatus.DISCONNECTED,
                        last_error="Repository access was revoked in GitHub App settings.",
                    )

        return Response(
            {"status": "success", "event": event_type, "action": action},
            status=status.HTTP_200_OK,
        )


class WorkspaceGitHubInstallationListView(APIView):
    """List or register authorized GitHub App installations for a workspace (GH-1)."""

    def get_permissions(self) -> list[permissions.BasePermission]:
        if self.request.method == "POST":
            return [permissions.IsAuthenticated(), IsWorkspaceAdmin(), IsGitHubAppEnabled()]
        return [permissions.IsAuthenticated(), IsWorkspaceMember(), IsGitHubAppEnabled()]

    @extend_schema(
        summary="List GitHub App Installations",
        description="Retrieve all GitHub App installations authorized for this workspace.",
        responses={200: GitHubAppInstallationSerializer(many=True)},
        tags=["GitHub Integration"],
    )
    def get(self, request: Request, workspace_id: uuid.UUID) -> Response:
        workspace = resolve_workspace(request, self)
        installations = GitHubAppInstallation.objects.filter(workspace=workspace, is_active=True)
        serializer = GitHubAppInstallationSerializer(installations, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Register GitHub App Installation",
        description="Record a newly authorized GitHub App installation for the workspace.",
        request=GitHubAppInstallationRegisterSerializer,
        responses={
            201: GitHubAppInstallationSerializer,
            400: OpenApiResponse(description="Validation error."),
        },
        tags=["GitHub Integration"],
    )
    def post(self, request: Request, workspace_id: uuid.UUID) -> Response:
        workspace = resolve_workspace(request, self)
        serializer = GitHubAppInstallationRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        installation, _ = GitHubAppInstallation.objects.update_or_create(
            installation_id=data["installation_id"],
            defaults={
                "workspace": workspace,
                "account_login": data["account_login"],
                "account_type": data.get("account_type", "User"),
                "repository_selection": data.get("repository_selection", "selected"),
                "permissions": data.get("permissions", {}),
                "is_active": True,
                "suspended_at": None,
            },
        )

        record_audit_event(
            action="GITHUB_APP_INSTALLED",
            request=request,
            workspace_id=workspace.id,
            actor=request.user if request.user.is_authenticated else None,
            resource_type="GitHubAppInstallation",
            resource_id=str(installation.id),
            payload={
                "installation_id": installation.installation_id,
                "account_login": installation.account_login,
            },
        )

        out_serializer = GitHubAppInstallationSerializer(installation)
        return Response(out_serializer.data, status=status.HTTP_201_CREATED)


class WorkspaceGitHubInstallationDetailView(APIView):
    """Retrieve or disconnect an authorized GitHub App installation."""

    def get_permissions(self) -> list[permissions.BasePermission]:
        if self.request.method == "DELETE":
            return [permissions.IsAuthenticated(), IsWorkspaceAdmin(), IsGitHubAppEnabled()]
        return [permissions.IsAuthenticated(), IsWorkspaceMember(), IsGitHubAppEnabled()]

    @extend_schema(
        summary="Get GitHub App Installation Details",
        responses={
            200: GitHubAppInstallationSerializer,
            404: OpenApiResponse(description="Installation not found."),
        },
        tags=["GitHub Integration"],
    )
    def get(self, request: Request, workspace_id: uuid.UUID, installation_id: int) -> Response:
        workspace = resolve_workspace(request, self)
        inst = GitHubAppInstallation.objects.filter(
            workspace=workspace, installation_id=installation_id
        ).first()
        if not inst:
            raise NotFound("GitHub App installation not found.")
        serializer = GitHubAppInstallationSerializer(inst)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Deactivate GitHub App Installation",
        responses={
            204: OpenApiResponse(description="Installation deactivated."),
            404: OpenApiResponse(description="Installation not found."),
        },
        tags=["GitHub Integration"],
    )
    def delete(self, request: Request, workspace_id: uuid.UUID, installation_id: int) -> Response:
        workspace = resolve_workspace(request, self)
        inst = GitHubAppInstallation.objects.filter(
            workspace=workspace, installation_id=installation_id
        ).first()
        if not inst:
            raise NotFound("GitHub App installation not found.")

        inst.is_active = False
        inst.save(update_fields=["is_active", "updated_at"])

        SiteGitHubRepoConnection.objects.filter(installation=inst).update(
            integration_status=IntegrationStatus.DISCONNECTED,
            last_error="Installation removed by workspace administrator.",
        )

        record_audit_event(
            action="GITHUB_APP_UNINSTALLED",
            request=request,
            workspace_id=workspace.id,
            actor=request.user if request.user.is_authenticated else None,
            resource_type="GitHubAppInstallation",
            resource_id=str(inst.id),
            payload={"installation_id": inst.installation_id},
        )

        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkspaceGitHubInstallationRepositoriesView(APIView):
    """List accessible repositories for an installation (GH-2)."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceMember, IsGitHubAppEnabled)

    @extend_schema(
        summary="List Accessible Repositories",
        description="Query GitHub for repositories accessible under this authorized installation.",
        responses={200: OpenApiResponse(description="List of accessible repository objects.")},
        tags=["GitHub Integration"],
    )
    def get(self, request: Request, workspace_id: uuid.UUID, installation_id: int) -> Response:
        workspace = resolve_workspace(request, self)
        inst = GitHubAppInstallation.objects.filter(
            workspace=workspace, installation_id=installation_id, is_active=True
        ).first()
        if not inst:
            raise NotFound("Active GitHub App installation not found.")

        client = get_github_client()
        repositories = client.list_installation_repositories(inst.installation_id)
        return Response({"repositories": repositories}, status=status.HTTP_200_OK)


class SiteGitHubConnectionView(APIView):
    """Retrieve or disconnect repository connection for a site (GH-2)."""

    def get_permissions(self) -> list[permissions.BasePermission]:
        if self.request.method == "DELETE":
            return [permissions.IsAuthenticated(), IsWorkspaceAdmin(), IsGitHubAppEnabled()]
        return [permissions.IsAuthenticated(), IsWorkspaceMember(), IsGitHubAppEnabled()]

    @extend_schema(
        summary="Get Site GitHub Connection",
        responses={
            200: SiteGitHubRepoConnectionSerializer,
            404: OpenApiResponse(description="Connection not found."),
        },
        tags=["GitHub Integration"],
    )
    def get(self, request: Request, workspace_id: uuid.UUID, site_id: uuid.UUID) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)
        connection = getattr(site, "github_connection", None)
        if not connection:
            raise NotFound("No GitHub repository connected to this site.")
        serializer = SiteGitHubRepoConnectionSerializer(connection)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Disconnect Site GitHub Repository",
        responses={
            204: OpenApiResponse(description="Repository disconnected."),
            404: OpenApiResponse(description="Connection not found."),
        },
        tags=["GitHub Integration"],
    )
    def delete(self, request: Request, workspace_id: uuid.UUID, site_id: uuid.UUID) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)
        connection = getattr(site, "github_connection", None)
        if not connection:
            raise NotFound("No GitHub repository connected to this site.")

        repo_name = connection.repo_full_name
        connection.delete()

        record_audit_event(
            action="GITHUB_REPO_DISCONNECTED",
            request=request,
            workspace_id=workspace.id,
            actor=request.user if request.user.is_authenticated else None,
            resource_type="SiteGitHubRepoConnection",
            resource_id=str(site.id),
            payload={"repo_full_name": repo_name},
        )

        return Response(status=status.HTTP_204_NO_CONTENT)


class SiteGitHubConnectView(APIView):
    """Connect an authorized GitHub repository and branch to a site (GH-2)."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceAdmin, IsGitHubAppEnabled)

    @extend_schema(
        summary="Connect GitHub Repository to Site",
        description="Link a repository and branch from an authorized installation to a site.",
        request=GitHubRepoConnectSerializer,
        responses={
            200: SiteGitHubRepoConnectionSerializer,
            400: OpenApiResponse(description="Validation error or branch not found."),
            404: OpenApiResponse(description="Site or installation not found."),
        },
        tags=["GitHub Integration"],
    )
    def post(self, request: Request, workspace_id: uuid.UUID, site_id: uuid.UUID) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)

        serializer = GitHubRepoConnectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        inst = GitHubAppInstallation.objects.filter(
            workspace=workspace,
            installation_id=data["installation_id"],
            is_active=True,
        ).first()
        if not inst:
            raise NotFound("Active GitHub App installation not found in this workspace.")

        repo_full_name = data["repo_full_name"]
        selected_branch = data.get("selected_branch", "main")

        client = get_github_client()
        # Verify branch existence via client
        branch_info = client.get_repository_branch(repo_full_name, selected_branch)
        default_branch = "main"
        if branch_info.get("name"):
            default_branch = branch_info["name"]

        connection, _ = SiteGitHubRepoConnection.objects.update_or_create(
            site=site,
            defaults={
                "installation": inst,
                "repo_full_name": repo_full_name,
                "default_branch": default_branch,
                "selected_branch": selected_branch,
                "integration_status": IntegrationStatus.CONNECTED,
                "last_synced_at": timezone.now(),
                "last_error": "",
            },
        )

        record_audit_event(
            action="GITHUB_REPO_CONNECTED",
            request=request,
            workspace_id=workspace.id,
            actor=request.user if request.user.is_authenticated else None,
            resource_type="SiteGitHubRepoConnection",
            resource_id=str(connection.id),
            payload={
                "site_id": str(site.id),
                "repo_full_name": repo_full_name,
                "selected_branch": selected_branch,
            },
        )

        out_serializer = SiteGitHubRepoConnectionSerializer(connection)
        return Response(out_serializer.data, status=status.HTTP_200_OK)


class SiteGitHubAnalyzeView(APIView):
    """Analyze connected repository manifests safely as untrusted data (GH-3, GH-5)."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceMember, IsGitHubAppEnabled)

    @extend_schema(
        summary="Analyze Repository Framework",
        description=(
            "Inspect manifest files strictly as untrusted data to detect frontend framework."
        ),
        request=None,
        responses={
            200: FrameworkDetectionResponseSerializer,
            400: OpenApiResponse(description="Manifest validation error."),
            404: OpenApiResponse(description="Connected repository not found."),
        },
        tags=["GitHub Integration"],
    )
    def post(self, request: Request, workspace_id: uuid.UUID, site_id: uuid.UUID) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)
        connection = getattr(site, "github_connection", None)
        if not connection:
            raise NotFound("No GitHub repository connected to this site.")

        client = get_github_client()
        # Candidate manifests to fetch
        manifest_paths = [
            "package.json",
            "next.config.js",
            "next.config.mjs",
            "next.config.ts",
            "vite.config.js",
            "vite.config.ts",
            "astro.config.mjs",
            "nuxt.config.ts",
            "remix.config.js",
        ]

        files = client.get_repository_files(
            connection.repo_full_name, connection.selected_branch, manifest_paths
        )

        analysis = analyze_repository_manifests(files)

        # Update connection model
        connection.detected_framework = analysis["detected_framework"]
        connection.framework_manifest = analysis["manifest_summary"]
        connection.integration_status = IntegrationStatus.ANALYZED
        connection.last_synced_at = timezone.now()
        connection.save(
            update_fields=[
                "detected_framework",
                "framework_manifest",
                "integration_status",
                "last_synced_at",
                "updated_at",
            ]
        )

        record_audit_event(
            action="GITHUB_FRAMEWORK_ANALYZED",
            request=request,
            workspace_id=workspace.id,
            actor=request.user if request.user.is_authenticated else None,
            resource_type="SiteGitHubRepoConnection",
            resource_id=str(connection.id),
            payload={
                "detected_framework": analysis["detected_framework"],
                "confidence": analysis["confidence"],
            },
        )

        serializer = FrameworkDetectionResponseSerializer(analysis)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SiteGitHubIntegrationPRView(APIView):
    """Open integration pull request with boilerplate client configuration (GH-4)."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceAdmin, IsGitHubAppEnabled)

    @extend_schema(
        summary="Open Integration Pull Request",
        description=(
            "Creates an integration branch and opens a Pull Request with boilerplate code. "
            "Never commits to default branch."
        ),
        request=IntegrationPROpenSerializer,
        responses={
            201: IntegrationPRResponseSerializer,
            400: OpenApiResponse(description="Branch validation or git error."),
            404: OpenApiResponse(description="Connection not found."),
        },
        tags=["GitHub Integration"],
    )
    def post(self, request: Request, workspace_id: uuid.UUID, site_id: uuid.UUID) -> Response:
        workspace = resolve_workspace(request, self)
        site = _get_site(workspace, site_id)
        connection = getattr(site, "github_connection", None)
        if not connection:
            raise NotFound("No GitHub repository connected to this site.")

        serializer = IntegrationPROpenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        client = get_github_client()
        base_branch = connection.selected_branch
        new_branch = data.get("branch_name") or f"cms-integration-{site.slug}"

        # Safety check: Cannot commit directly to base branch (GH-4)
        if new_branch == base_branch:
            raise ValidationError(
                {"branch_name": "Integration branch cannot be the same as the base branch."}
            )

        public_api_url = getattr(settings, "PUBLIC_API_URL", "http://localhost:8000")
        files = generate_integration_patch_files(
            framework=connection.detected_framework,
            site_slug=site.slug,
            public_api_url=public_api_url,
        )

        pr_record = client.create_branch_and_pull_request(
            repo_full_name=connection.repo_full_name,
            base_branch=base_branch,
            new_branch=new_branch,
            commit_message=data["commit_message"],
            pr_title=data["pr_title"],
            pr_body=data["pr_body"],
            files=files,
        )

        connection.integration_status = IntegrationStatus.PR_OPENED
        connection.last_pr_url = pr_record["pr_url"]
        connection.last_pr_number = pr_record["pr_number"]
        connection.last_synced_at = timezone.now()
        connection.save(
            update_fields=[
                "integration_status",
                "last_pr_url",
                "last_pr_number",
                "last_synced_at",
                "updated_at",
            ]
        )

        record_audit_event(
            action="GITHUB_PR_OPENED",
            request=request,
            workspace_id=workspace.id,
            actor=request.user if request.user.is_authenticated else None,
            resource_type="SiteGitHubRepoConnection",
            resource_id=str(connection.id),
            payload={
                "pr_number": pr_record["pr_number"],
                "pr_url": pr_record["pr_url"],
                "new_branch": new_branch,
            },
        )

        out_serializer = IntegrationPRResponseSerializer(pr_record)
        return Response(out_serializer.data, status=status.HTTP_201_CREATED)
