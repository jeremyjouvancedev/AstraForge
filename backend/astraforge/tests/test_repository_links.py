import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from astraforge.accounts.models import Workspace
from astraforge.integrations.models import RepositoryLink

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return get_user_model().objects.create_user(
        username="operator", password="s3cretpass"
    )


@pytest.fixture
def workspace(user):
    return Workspace.ensure_default_for_user(user)


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_create_gitlab_link_defaults_to_public_url(api_client, user, workspace):
    payload = {
        "provider": "gitlab",
        "repository": "org/project",
        "access_token": "fake-token-3456",
        "workspace_uid": workspace.uid,
    }
    response = api_client.post(
        reverse("repository-link-list"), payload, format="json"
    )
    assert response.status_code == 201
    link = RepositoryLink.objects.get(workspace=workspace)
    assert link.base_url == RepositoryLink.DEFAULT_GITLAB_URL
    data = response.json()
    assert "token_preview" not in data
    assert "access_token" not in data
    assert data["workspace"]["uid"] == workspace.uid


def test_create_github_link_rejects_custom_base_url(api_client, workspace):
    payload = {
        "provider": "github",
        "repository": "org/app",
        "access_token": "fake-token-4567",
        "base_url": "https://custom.example.com",
        "workspace_uid": workspace.uid,
    }
    response = api_client.post(
        reverse("repository-link-list"), payload, format="json"
    )
    assert response.status_code == 400
    assert "base_url" in response.json()


def test_list_links_returns_masked_tokens(api_client, user, workspace):
    RepositoryLink.objects.create(
        user=user,
        workspace=workspace,
        provider=RepositoryLink.Provider.GITHUB,
        repository="org/app",
        access_token="fake-token-ABCD",
    )
    response = api_client.get(reverse("repository-link-list"))
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert "token_preview" not in payload[0]
    assert "access_token" not in payload[0]
    assert payload[0]["workspace"]["uid"] == workspace.uid


def test_link_endpoints_require_auth():
    client = APIClient()
    response = client.get(reverse("repository-link-list"))
    assert response.status_code == 403
