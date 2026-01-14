import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from astraforge.accounts.models import Workspace
from astraforge.sandbox.models import SandboxSession

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return get_user_model().objects.create_user(username="usage-user", password="pass12345")


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_workspace_usage_endpoint(api_client, user):
    workspace = Workspace.ensure_default_for_user(user)
    SandboxSession.objects.create(
        user=user,
        workspace=workspace,
        mode=SandboxSession.Mode.DOCKER,
        image="astraforge/codex-cli:latest",
        status=SandboxSession.Status.READY,
    )
    url = reverse("workspace-usage", args=[workspace.uid])
    response = api_client.get(url)
    assert response.status_code == 200
    payload = response.json()
    assert payload["plan"] == workspace.plan
    assert payload["usage"]["active_sandboxes"] == 1
    assert payload["usage"]["sandbox_seconds"] >= 0
    assert payload["usage"]["artifacts_bytes"] >= 0
    assert "limits" in payload
    assert "catalog" in payload
    assert "trial" in payload["catalog"]


def test_workspace_usage_rejects_foreign_workspace(api_client):
    other_user = get_user_model().objects.create_user(username="foreign", password="pass12345")
    foreign_workspace = Workspace.ensure_default_for_user(other_user)
    url = reverse("workspace-usage", args=[foreign_workspace.uid])
    response = api_client.get(url)
    assert response.status_code == 404
