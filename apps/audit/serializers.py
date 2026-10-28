"""Serializers for audit trail events."""

from rest_framework import serializers

from apps.audit.models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer[AuditEvent]):
    class Meta:
        model = AuditEvent
        fields = (
            "id",
            "workspace_id",
            "actor_id",
            "actor_email",
            "action",
            "resource_type",
            "resource_id",
            "ip_address",
            "user_agent",
            "payload",
            "timestamp",
        )
        read_only_fields = fields
