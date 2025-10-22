import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from astraforge.accounts.models import ApiKey

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return get_user_model().objects.create_user(username="owner", password="pass12345")


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def anonymous_client():
    return APIClient()


def test_create_api_key_returns_plaintext(api_client, user):
    response = api_client.post(reverse("api-key-list"), {"name": "ci"})
    assert response.status_code == 201
    data = response.json()
    assert "key" in data and data["key"]
    assert ApiKey.objects.filter(user=user, name="ci").exists()


def test_list_api_keys(api_client, user):
    ApiKey.create_key(user=user, name="integration")
    response = api_client.get(reverse("api-key-list"))
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["name"] == "integration"


def test_delete_api_key_marks_inactive(api_client, user):
    api_key, _ = ApiKey.create_key(user=user, name="temp")
    response = api_client.delete(reverse("api-key-detail", args=[api_key.id]))
    assert response.status_code == 204
    api_key.refresh_from_db()
    assert not api_key.is_active


def test_api_key_authentication_allows_access_to_requests(user, anonymous_client):
    api_key, raw_key = ApiKey.create_key(user=user, name="integration")
    response = anonymous_client.get(reverse("request-list"), HTTP_X_API_KEY=raw_key)
    # list endpoint returns [] but requires auth; API key should grant access
    assert response.status_code == 200
