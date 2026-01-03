import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from rest_framework.test import APIClient

from astraforge.accounts.models import UserAccess

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    client = APIClient(enforce_csrf_checks=False)
    return client


def test_register_waitlists_user_by_default(settings, api_client):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    response = api_client.post(
        reverse("auth-register"),
        {
            "username": "newuser",
            "password": "strongpass123",
            "email": "user@example.com",
        },
        format="json",
    )
    assert response.status_code == 202
    data = response.json()
    assert data["username"] == "newuser"
    assert data["access"]["status"] == "pending"
    assert data["access"]["waitlist_email_sent"] is True
    user = get_user_model().objects.get(username="newuser")
    assert user.email == "user@example.com"
    access = UserAccess.objects.get(user=user)
    assert access.status == "pending"
    assert access.waitlist_notified_at is not None
    assert "sessionid" not in response.cookies


def test_login_rejects_when_access_pending(api_client):
    user_model = get_user_model()
    user_model.objects.create_user(username="alice", password="strongpass123")
    UserAccess.for_user(user_model.objects.get(username="alice"))

    response = api_client.post(
        reverse("auth-login"),
        {"username": "alice", "password": "strongpass123"},
        format="json",
    )
    assert response.status_code == 403
    assert response.json()["access"]["status"] == "pending"


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
    user = user_model.objects.create_user(username="bob", password="strongpass123")
    UserAccess.for_user(user).approve()

    login_response = api_client.post(
        reverse("auth-login"),
        {"username": "bob", "password": "strongpass123"},
        format="json",
    )
    assert login_response.status_code == 200

    response = api_client.post(reverse("auth-logout"))
    assert response.status_code == 204


def test_login_allows_approved_user(api_client):
    user_model = get_user_model()
    user = user_model.objects.create_user(username="carol", password="strongpass123")
    access = UserAccess.for_user(user)
    access.approve()

    response = api_client.post(
        reverse("auth-login"),
        {"username": "carol", "password": "strongpass123"},
        format="json",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "carol"
    assert data["access"]["status"] == "approved"
    assert "sessionid" in response.cookies


def test_waitlist_can_be_disabled(settings, api_client):
    settings.AUTH_REQUIRE_APPROVAL = False
    settings.AUTH_WAITLIST_ENABLED = False
    user_model = get_user_model()
    user_model.objects.create_user(username="dave", password="strongpass123")

    response = api_client.post(
        reverse("auth-login"),
        {"username": "dave", "password": "strongpass123"},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["access"]["status"] == "approved"
    assert "sessionid" in response.cookies


def test_auth_settings_endpoint(api_client):
    response = api_client.get(reverse("auth-settings"))
    assert response.status_code == 200
    data = response.json()
    assert set(
        [
            "require_approval",
            "allow_all_users",
            "waitlist_enabled",
            "self_hosted",
            "billing_enabled",
        ]
    ).issubset(data.keys())


def test_waitlist_email_sent_once(settings, api_client):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.AUTH_REQUIRE_APPROVAL = True
    settings.AUTH_ALLOW_ALL_USERS = False

    response = api_client.post(
        reverse("auth-register"),
        {
            "username": "erin",
            "password": "strongpass123",
            "email": "erin@example.com",
        },
        format="json",
    )
    assert response.status_code == 202
    assert len(mail.outbox) == 1
    access = UserAccess.objects.get(user__username="erin")
    assert access.waitlist_notified_at is not None

    # Pending login should not send additional mail
    response = api_client.post(
        reverse("auth-login"),
        {"username": "erin", "password": "strongpass123"},
        format="json",
    )
    assert response.status_code == 403
    assert len(mail.outbox) == 1
