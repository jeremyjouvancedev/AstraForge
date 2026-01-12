import json

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from astraforge.computer_use.models import ComputerUseRun

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return get_user_model().objects.create_user(
        username="trace-user", password="pass12345"
    )


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _write_timeline(run_dir, screenshot_value="c2NyZWVuc2hvdA=="):
    items = [
        {
            "type": "computer_call",
            "call_id": "call-1",
            "action": {"type": "visit_url", "url": "https://example.com"},
            "meta": {"done": False, "critical_point": False},
            "pending_safety_checks": [],
        },
        {
            "type": "computer_call_output",
            "call_id": "call-1",
            "output": {
                "url": "https://example.com",
                "viewport": {"w": 1280, "h": 720},
                "screenshot_b64": screenshot_value,
                "execution": {"status": "ok"},
            },
        },
    ]
    timeline_path = run_dir / "timeline.jsonl"
    timeline_path.write_text(
        "\n".join(json.dumps(item) for item in items) + "\n",
        encoding="utf-8",
    )
    return items


def test_timeline_omits_screenshots_by_default(api_client, user, tmp_path, monkeypatch):
    root = tmp_path / "computer-use"
    run_dir = root / "run-1"
    run_dir.mkdir(parents=True)
    _write_timeline(run_dir)
    monkeypatch.setenv("COMPUTER_USE_TRACE_DIR", str(root))

    run = ComputerUseRun.objects.create(
        user=user,
        goal="Check example",
        status=ComputerUseRun.Status.COMPLETED,
        trace_dir=str(run_dir),
    )
    url = reverse("computer-use-run-timeline", kwargs={"pk": run.id})
    response = api_client.get(url)

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 2
    assert payload["items"][1]["output"]["screenshot_b64"] == ""


def test_timeline_includes_screenshots_when_requested(api_client, user, tmp_path, monkeypatch):
    root = tmp_path / "computer-use"
    run_dir = root / "run-2"
    run_dir.mkdir(parents=True)
    screenshot = "Zm9vYmFy"
    _write_timeline(run_dir, screenshot_value=screenshot)
    monkeypatch.setenv("COMPUTER_USE_TRACE_DIR", str(root))

    run = ComputerUseRun.objects.create(
        user=user,
        goal="Check example",
        status=ComputerUseRun.Status.COMPLETED,
        trace_dir=str(run_dir),
    )
    url = reverse("computer-use-run-timeline", kwargs={"pk": run.id})
    response = api_client.get(f"{url}?include_screenshots=1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][1]["output"]["screenshot_b64"] == screenshot


def test_timeline_respects_limit(api_client, user, tmp_path, monkeypatch):
    root = tmp_path / "computer-use"
    run_dir = root / "run-3"
    run_dir.mkdir(parents=True)
    _write_timeline(run_dir)
    monkeypatch.setenv("COMPUTER_USE_TRACE_DIR", str(root))

    run = ComputerUseRun.objects.create(
        user=user,
        goal="Check example",
        status=ComputerUseRun.Status.COMPLETED,
        trace_dir=str(run_dir),
    )
    url = reverse("computer-use-run-timeline", kwargs={"pk": run.id})
    response = api_client.get(f"{url}?limit=1&include_screenshots=1")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 1
