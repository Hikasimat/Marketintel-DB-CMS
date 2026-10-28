"""Accounts and authentication URL configuration."""

from django.urls import path

from apps.accounts.views import (
    CurrentUserView,
    LoginView,
    LogoutView,
    TokenRefreshView,
)

app_name = "accounts"

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="refresh"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/me/", CurrentUserView.as_view(), name="current_user"),
]
