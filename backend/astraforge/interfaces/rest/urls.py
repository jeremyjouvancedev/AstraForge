"""API URL routes for AstraForge REST interface."""

from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from astraforge.interfaces.rest.views import (
    ApiKeyViewSet,
    ChatViewSet,
    CsrfTokenView,
    CurrentUserView,
    ExecutionViewSet,
    LoginView,
    LogoutView,
    RepositoryLinkViewSet,
    PlanViewSet,
    RegisterView,
    RequestViewSet,
    RunLogStreamView,
)

router = DefaultRouter()
router.register(r"requests", RequestViewSet, basename="request")
router.register(r"chat", ChatViewSet, basename="chat")
router.register(r"api-keys", ApiKeyViewSet, basename="api-key")
router.register(r"repository-links", RepositoryLinkViewSet, basename="repository-link")

urlpatterns = [
    path("", include(router.urls)),
    path(
        "requests/plan/", PlanViewSet.as_view({"post": "create"}), name="request-plan"
    ),
    path(
        "requests/execute/",
        ExecutionViewSet.as_view({"post": "create"}),
        name="request-execute",
    ),
    path(
        "runs/<uuid:pk>/logs/stream", RunLogStreamView.as_view(), name="run-log-stream"
    ),
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", CurrentUserView.as_view(), name="auth-me"),
    path("auth/csrf/", CsrfTokenView.as_view(), name="auth-csrf"),
]
