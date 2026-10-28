"""Serializers for authentication and user accounts."""

from __future__ import annotations

from typing import Any

from django.contrib.auth import authenticate
from rest_framework import serializers

from apps.accounts.models import User


class LoginSerializer(serializers.Serializer[Any]):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        email = attrs.get("email", "").lower().strip()
        password = attrs.get("password", "")

        user = authenticate(email=email, password=password)
        if not user:
            # Fallback for manual check if default backend requires username
            try:
                candidate = User.objects.get(email=email)
                if candidate.check_password(password):
                    user = candidate
            except User.DoesNotExist:
                user = None

        if not user or not user.is_active:
            raise serializers.ValidationError("Invalid credentials or account inactive.")

        attrs["user"] = user
        return attrs


class TokenRefreshSerializer(serializers.Serializer[Any]):
    refresh = serializers.CharField()


class LogoutSerializer(serializers.Serializer[Any]):
    refresh = serializers.CharField()


class UserSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = ("id", "email", "is_active", "is_staff", "created_at")
        read_only_fields = fields
