import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from astraforge.integrations.models import RepositoryLink

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return get_user_model().objects.create_user(
        username="operator", password="s3cretpass"
    )


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_create_gitlab_link_defaults_to_public_url(api_client, user):
    payload = {
        "provider": "gitlab",
        "repository": "org/project",
        "access_token": "fake-token-3456",
    }
    response = api_client.post(
        reverse("repository-link-list"), payload, format="json"
    )
    assert response.status_code == 201
    link = RepositoryLink.objects.get(user=user)
    assert link.base_url == RepositoryLink.DEFAULT_GITLAB_URL
    data = response.json()
    assert data["token_preview"].endswith("3456")
    assert "access_token" not in data


def test_create_github_link_rejects_custom_base_url(api_client):
    payload = {
        "provider": "github",
        "repository": "org/app",
        "access_token": "fake-token-4567",
        "base_url": "https://custom.example.com",
    }
    response = api_client.post(
        reverse("repository-link-list"), payload, format="json"
    )
    assert response.status_code == 400
    assert "base_url" in response.json()


def test_list_links_returns_masked_tokens(api_client, user):
    RepositoryLink.objects.create(
        user=user,
        provider=RepositoryLink.Provider.GITHUB,
        repository="org/app",
        access_token="fake-token-ABCD",
    )
    response = api_client.get(reverse("repository-link-list"))
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["token_preview"].endswith("ABCD")
    assert "access_token" not in payload[0]


def test_link_endpoints_require_auth():
    client = APIClient()
    response = client.get(reverse("repository-link-list"))
    assert response.status_code == 403
