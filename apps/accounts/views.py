"""Authentication views for login, token refresh, logout, and current user info."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.serializers import (
    LoginSerializer,
    LogoutSerializer,
    TokenRefreshSerializer,
    UserSerializer,
)
from apps.accounts.tokens import (
    TokenReuseDetectedError,
    create_token_pair,
    refresh_token_pair,
    revoke_token_family,
)
from apps.common.errors import error_envelope
from apps.common.jwt import TokenExpiredError, TokenInvalidError


class LoginView(APIView):
    """Authenticate via email/password and obtain access + refresh tokens."""

    permission_classes = (permissions.AllowAny,)
    authentication_classes = ()

    @extend_schema(
        request=LoginSerializer,
        responses={
            200: OpenApiResponse(description="Tokens successfully issued"),
            400: OpenApiResponse(description="Invalid request or credentials"),
        },
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        token_data = create_token_pair(user)
        return Response(token_data, status=status.HTTP_200_OK)


class TokenRefreshView(APIView):
    """Rotate refresh token to obtain a new access token and refreshed lineage token."""

    permission_classes = (permissions.AllowAny,)
    authentication_classes = ()

    @extend_schema(
        request=TokenRefreshSerializer,
        responses={
            200: OpenApiResponse(description="Token successfully rotated"),
            401: OpenApiResponse(description="Token expired, invalid, or reused"),
        },
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = TokenRefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw_refresh = serializer.validated_data["refresh"]

        try:
            token_data = refresh_token_pair(raw_refresh)
            return Response(token_data, status=status.HTTP_200_OK)
        except TokenReuseDetectedError as exc:
            return Response(
                error_envelope(code="token_reuse_detected", message=str(exc)),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except TokenExpiredError as exc:
            return Response(
                error_envelope(code="token_expired", message=str(exc)),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except TokenInvalidError as exc:
            return Response(
                error_envelope(code="token_invalid", message=str(exc)),
                status=status.HTTP_401_UNAUTHORIZED,
            )


class LogoutView(APIView):
    """Revoke active refresh token family and terminate session."""

    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(
        request=LogoutSerializer,
        responses={
            204: OpenApiResponse(description="Session terminated"),
            400: OpenApiResponse(description="Invalid token payload"),
        },
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw_refresh = serializer.validated_data["refresh"]

        revoke_token_family(raw_refresh)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentUserView(APIView):
    """Retrieve details for the currently authenticated user."""

    permission_classes = (permissions.IsAuthenticated,)

    @extend_schema(
        responses={200: UserSerializer},
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        user = request.user
        if not isinstance(user, User):
            raise AuthenticationFailed("User not authenticated.")
        serializer = UserSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)
