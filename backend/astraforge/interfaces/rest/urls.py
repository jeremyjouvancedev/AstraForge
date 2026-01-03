"""API URL routes for AstraForge REST interface."""

from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from astraforge.interfaces.rest.views import (
    ApiKeyViewSet,
    ActivityLogViewSet,
    ChatViewSet,
    MergeRequestViewSet,
    CsrfTokenView,
    AuthSettingsView,
    CurrentUserView,
    EarlyAccessRequestView,
    ExecutionViewSet,
    LoginView,
    LogoutView,
    RepositoryLinkViewSet,
    PlanViewSet,
    RegisterView,
    RequestViewSet,
    RunViewSet,
    RunLogStreamView,
    DeepAgentConversationView,
    DeepAgentMessageView,
    WorkspaceViewSet,
)
from astraforge.sandbox.views import SandboxSessionViewSet

router = DefaultRouter()
router.register(r"requests", RequestViewSet, basename="request")
router.register(r"chat", ChatViewSet, basename="chat")
router.register(r"api-keys", ApiKeyViewSet, basename="api-key")
router.register(r"activity", ActivityLogViewSet, basename="activity-log")
router.register(r"repository-links", RepositoryLinkViewSet, basename="repository-link")
router.register(r"runs", RunViewSet, basename="run")
router.register(r"merge-requests", MergeRequestViewSet, basename="merge-request")
router.register(r"sandbox/sessions", SandboxSessionViewSet, basename="sandbox-session")
router.register(r"workspaces", WorkspaceViewSet, basename="workspace")

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
    path(
        "deepagent/conversations/",
        DeepAgentConversationView.as_view(),
        name="deepagent-conversations",
    ),
    path(
        "deepagent/conversations/<uuid:conversation_id>/messages/",
        DeepAgentMessageView.as_view(),
        name="deepagent-messages",
    ),
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", CurrentUserView.as_view(), name="auth-me"),
    path("auth/csrf/", CsrfTokenView.as_view(), name="auth-csrf"),
    path("auth/settings/", AuthSettingsView.as_view(), name="auth-settings"),
    path(
        "marketing/early-access/",
        EarlyAccessRequestView.as_view(),
        name="marketing-early-access",
    ),
]
