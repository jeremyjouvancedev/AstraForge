import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    client = APIClient(enforce_csrf_checks=False)
    return client


def test_register_creates_user_and_starts_session(api_client):
    response = api_client.post(
        reverse("auth-register"),
        {
            "username": "newuser",
            "password": "strongpass123",
            "email": "user@example.com",
        },
        format="json",
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "newuser"
    user = get_user_model().objects.get(username="newuser")
    assert user.email == "user@example.com"
    assert "sessionid" in response.cookies


def test_login_returns_session_cookie(api_client):
    user_model = get_user_model()
    user_model.objects.create_user(username="alice", password="strongpass123")

    response = api_client.post(
        reverse("auth-login"),
        {"username": "alice", "password": "strongpass123"},
        format="json",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "alice"
    assert "sessionid" in response.cookies


def test_login_rejects_invalid_credentials(api_client):
    response = api_client.post(
        reverse("auth-login"),
        {"username": "missing", "password": "badpass"},
        format="json",
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


def test_logout_clears_session(api_client):
    user_model = get_user_model()
    user_model.objects.create_user(username="bob", password="strongpass123")

    login_response = api_client.post(
        reverse("auth-login"),
        {"username": "bob", "password": "strongpass123"},
        format="json",
    )
    assert login_response.status_code == 200

    response = api_client.post(reverse("auth-logout"))
    assert response.status_code == 204
