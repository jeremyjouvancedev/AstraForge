import uuid

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from astraforge.accounts.models import Workspace, WorkspaceMember, WorkspaceRole
from astraforge.integrations.models import RepositoryLink
from astraforge.requests.models import RequestRecord

pytestmark = pytest.mark.django_db


def test_default_workspace_created_for_user():
    user = get_user_model().objects.create_user(
        username="workspace-user", password="pass12345"
    )
    workspace = Workspace.ensure_default_for_user(user)
    membership = WorkspaceMember.objects.filter(workspace=workspace, user=user).first()

    assert workspace is not None
    assert workspace.uid
    assert membership is not None
    assert membership.role == WorkspaceRole.OWNER


def test_request_creation_rejects_foreign_workspace(settings):
    settings.AUTH_REQUIRE_APPROVAL = False
    user = get_user_model().objects.create_user(
        username="owner", password="pass12345", email="owner@example.com"
    )
    workspace = Workspace.ensure_default_for_user(user)
    client = APIClient()
    client.force_authenticate(user=user)

    repo_link = RepositoryLink.objects.create(
        user=user,
        workspace=workspace,
        provider=RepositoryLink.Provider.GITHUB,
        repository="org/repo",
        access_token="token",
    )

    other_user = get_user_model().objects.create_user(
        username="other", password="pass12345", email="other@example.com"
    )
    foreign_workspace = Workspace.ensure_default_for_user(other_user)

    response = client.post(
        reverse("request-list"),
        {
            "tenant_id": foreign_workspace.uid,
            "project_id": str(repo_link.id),
            "prompt": "Do something important",
            "source": "direct_user",
        },
        format="json",
    )
    assert response.status_code == 400
    assert "tenant_id" in response.json()


def test_request_list_filters_by_workspace_membership(settings):
    settings.AUTH_REQUIRE_APPROVAL = False
    user = get_user_model().objects.create_user(
        username="scoped", password="pass12345", email="scoped@example.com"
    )
    allowed_workspace = Workspace.ensure_default_for_user(user)
    client = APIClient()
    client.force_authenticate(user=user)

    permitted_request = RequestRecord.objects.create(
        id=uuid.uuid4(),
        user=user,
        tenant_id=allowed_workspace.uid,
        source="direct_user",
        sender="scoped@example.com",
        payload={"title": "Allowed", "description": "ok", "context": {}, "attachments": []},
        state="pending",
        artifacts={},
        metadata={},
    )

    forbidden_workspace = Workspace.objects.create(
        uid="foreign-space", name="Foreign Space"
    )
    forbidden_request = RequestRecord.objects.create(
        id=uuid.uuid4(),
        user=user,
        tenant_id=forbidden_workspace.uid,
        source="direct_user",
        sender="scoped@example.com",
        payload={"title": "Forbidden", "description": "bad", "context": {}, "attachments": []},
        state="pending",
        artifacts={},
        metadata={},
    )

    response = client.get(reverse("request-list"))
    assert response.status_code == 200
    data = response.json()
    returned_ids = {entry["id"] for entry in data}
    assert str(permitted_request.id) in returned_ids
    assert str(forbidden_request.id) not in returned_ids


def test_workspace_creation_endpoint(settings):
    settings.AUTH_REQUIRE_APPROVAL = False
    user = get_user_model().objects.create_user(
        username="creator", password="pass12345", email="creator@example.com"
    )
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        reverse("workspace-list"),
        {"name": "New Workspace"},
        format="json",
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "New Workspace"
    assert data["uid"]
    workspace = Workspace.objects.get(uid=data["uid"])
    membership = WorkspaceMember.objects.filter(workspace=workspace, user=user).first()
    assert membership is not None
    assert membership.role == WorkspaceRole.OWNER
