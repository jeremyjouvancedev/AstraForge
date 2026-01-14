import pytest
from django.core import mail
from django.urls import reverse
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient(enforce_csrf_checks=False)


def test_early_access_request_sends_emails(settings, api_client):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.EARLY_ACCESS_NOTIFICATION_EMAIL = "founder@example.com"

    response = api_client.post(
        reverse("marketing-early-access"),
        {
            "email": "builder@example.com",
            "team_role": "Platform Engineering",
            "project_summary": "DeepAgents that patch repos and deploy infra.",
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["user_email_sent"] is True
    assert data["owner_email_sent"] is True
    assert len(mail.outbox) == 2
    assert mail.outbox[0].to == ["builder@example.com"]
    assert mail.outbox[1].to == ["founder@example.com"]


def test_early_access_request_handles_missing_owner(settings, api_client):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.EARLY_ACCESS_NOTIFICATION_EMAIL = ""

    response = api_client.post(
        reverse("marketing-early-access"),
        {
            "email": "ops@example.com",
            "team_role": "",
            "project_summary": "",
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["user_email_sent"] is True
    assert data["owner_email_sent"] is False
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["ops@example.com"]


def test_early_access_request_surfaces_mail_failure(monkeypatch, settings, api_client):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.EARLY_ACCESS_NOTIFICATION_EMAIL = "founder@example.com"

    from astraforge.accounts import emails as email_module

    def boom(**kwargs):
        raise RuntimeError("SMTP unavailable")

    monkeypatch.setattr(email_module, "send_early_access_confirmation", boom)

    response = api_client.post(
        reverse("marketing-early-access"),
        {
            "email": "ops@example.com",
            "team_role": "platform",
            "project_summary": "agents",
        },
        format="json",
    )

    assert response.status_code == 502
    data = response.json()
    assert data["user_email_sent"] is False
    assert data["owner_email_sent"] is False
