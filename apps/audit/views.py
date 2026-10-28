"""Views for inspecting workspace audit trail logs."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditEvent
from apps.audit.serializers import AuditEventSerializer
from apps.common.pagination import DefaultPagination
from apps.tenancy.permissions import IsWorkspaceAdmin, resolve_workspace


class WorkspaceAuditLogListView(APIView):
    """Retrieve immutable audit trail records for a workspace."""

    permission_classes = (permissions.IsAuthenticated, IsWorkspaceAdmin)
    pagination_class = DefaultPagination

    @extend_schema(responses={200: AuditEventSerializer(many=True)})
    def get(self, request: Request, workspace_id: str, *args: Any, **kwargs: Any) -> Response:
        workspace = resolve_workspace(request, self)
        events = AuditEvent.objects.filter(workspace_id=workspace.id).order_by("-timestamp")

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(events, request, view=self)
        if page is not None:
            serializer = AuditEventSerializer(page, many=True)
            return paginator.get_paginated_response(list(serializer.data))

        serializer = AuditEventSerializer(events, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
