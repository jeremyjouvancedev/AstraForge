import uuid

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from astraforge.application.use_cases import ExecuteRequest, ProcessRequest
from astraforge.domain.models.request import Request, RequestPayload, RequestState
from astraforge.domain.models.spec import DevelopmentSpec
from astraforge.domain.models.workspace import ExecutionOutcome, WorkspaceContext
from astraforge.infrastructure.repositories.memory import InMemoryRequestRepository
from astraforge.integrations.models import RepositoryLink

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return get_user_model().objects.create_user(
        username="requester", password="pass12345"
    )


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def request_payload():
    def _build(project_id: uuid.UUID):
        return {
            "tenant_id": "tenant-default",
            "source": "direct_user",
            "sender": "requester@example.com",
            "project_id": str(project_id),
            "payload": {
                "title": "Fix flaky test",
                "description": "Stabilize the integration suite by adding retries.",
            },
        }

    return _build


def test_create_request_requires_project(api_client, request_payload):
    body = request_payload(uuid.uuid4())
    response = api_client.post(
        reverse("request-list"), body, format="json"
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Link a project before submitting requests."
    }


def test_create_request_succeeds_with_project(api_client, user, request_payload, monkeypatch):
    captured = {}

    def fake_delay(request_id: str):
        captured["id"] = request_id

    monkeypatch.setattr(
        "astraforge.interfaces.rest.views.app_tasks.generate_spec_task.delay",
        fake_delay,
    )

    RepositoryLink.objects.create(
        user=user,
        provider=RepositoryLink.Provider.GITLAB,
        repository="org/project",
        access_token="token-123",
    )
    link = RepositoryLink.objects.get(user=user)

    body = request_payload(link.id)
    response = api_client.post(
        reverse("request-list"), body, format="json"
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["payload"]["title"] == body["payload"]["title"]
    assert payload["project"]["id"] == str(link.id)
    assert payload["state"] == "RECEIVED"
    assert payload["metadata"]["project"]["repository"] == "org/project"
    assert payload["metadata"].get("spec") is None
    assert captured.get("id") == payload["id"]


def test_create_request_preserves_description_whitespace(api_client, user, request_payload, monkeypatch):
    RepositoryLink.objects.create(
        user=user,
        provider=RepositoryLink.Provider.GITLAB,
        repository="org/project",
        access_token="token-123",
    )
    link = RepositoryLink.objects.get(user=user)

    monkeypatch.setattr(
        "astraforge.interfaces.rest.views.app_tasks.generate_spec_task.delay",
        lambda request_id: None,
    )

    body = request_payload(link.id)
    raw_description = "   Improve build pipeline?\n\nAdd caching please.   "
    body["payload"]["description"] = raw_description

    response = api_client.post(reverse("request-list"), body, format="json")

    assert response.status_code == 201
    payload = response.json()
    assert payload["payload"]["description"] == raw_description


def test_create_request_rejects_unknown_project(api_client, user, request_payload):
    RepositoryLink.objects.create(
        user=user,
        provider=RepositoryLink.Provider.GITLAB,
        repository="org/project",
        access_token="token-123",
    )
    other_user = get_user_model().objects.create_user(
        username="stranger", password="pass12345"
    )
    foreign_link = RepositoryLink.objects.create(
        user=other_user,
        provider=RepositoryLink.Provider.GITHUB,
        repository="elsewhere/repo",
        access_token="token-456",
    )

    body = request_payload(foreign_link.id)
    response = api_client.post(
        reverse("request-list"), body, format="json"
    )

    assert response.status_code == 400
    assert response.json() == {
        "project_id": ["Select a project linked to your account."]
    }


class _StubSpecGenerator:
    def generate(self, request: Request) -> DevelopmentSpec:
        return DevelopmentSpec(
            title=f"Spec for {request.payload.title}",
            summary="Implementation summary",
            requirements=["req"],
            implementation_steps=["step"],
        )


class _StubWorkspaceOperator:
    def __init__(self):
        self.prepared = False
        self.executed = False
        self.teardown_called = False

    def prepare(self, request: Request, spec: DevelopmentSpec, *, stream):
        self.prepared = True
        stream({"type": "status", "stage": "workspace", "message": "prepared"})
        return WorkspaceContext(
            ref="docker://stub",
            mode="docker",
            repository=request.metadata["project"]["repository"],
            branch="main",
            path="/workspace",
        )

    def run_codex(self, request: Request, spec: DevelopmentSpec, workspace: WorkspaceContext, *, stream):
        self.executed = True
        stream({"type": "status", "stage": "codex", "message": "running"})
        return ExecutionOutcome(diff="diff")

    def teardown(self, workspace: WorkspaceContext) -> None:
        self.teardown_called = True


class _StubRunLog:
    def __init__(self):
        self.events: list[dict[str, object]] = []

    def publish(self, request_id: str, event: dict[str, object]) -> None:
        self.events.append(event)

    def stream(self, request_id: str):  # pragma: no cover - not used in test
        return iter(self.events)


def test_process_request_populates_metadata():
    repo = InMemoryRequestRepository()
    payload = RequestPayload(title="Add feature", description="desc", context={})
    request = Request(
        id="req-1",
        tenant_id="tenant",
        source="direct_user",
        sender="user@example.com",
        payload=payload,
        metadata={
            "project": {
                "repository": "org/project",
                "branch": "main",
            }
        },
    )
    repo.save(request)
    run_log = _StubRunLog()

    spec = ProcessRequest(
        repository=repo,
        spec_generator=_StubSpecGenerator(),
        run_log=run_log,
    )(request_id="req-1")

    stored = repo.get("req-1")
    assert stored.state == RequestState.SPEC_READY
    assert stored.metadata["spec"]["title"].startswith("Spec for")
    assert "workspace" not in stored.metadata
    assert run_log.events[-1]["type"] == "spec_ready"
    assert spec.summary == "Implementation summary"


def test_chat_endpoint_preserves_message_whitespace(api_client, monkeypatch):
    captured: dict[str, dict[str, object]] = {}

    class _RunLogStub:
        def publish(self, request_id: str, event: dict[str, object]) -> None:
            captured["event"] = event

    monkeypatch.setattr(
        "astraforge.interfaces.rest.views.container.resolve_run_log",
        lambda: _RunLogStub(),
    )

    raw_message = "  keep my spacing please  "
    body = {"request_id": str(uuid.uuid4()), "message": raw_message}

    response = api_client.post(reverse("chat-list"), body, format="json")

    assert response.status_code == 202
    assert captured["event"]["message"] == raw_message


def test_execute_request_runs_workspace():
    repo = InMemoryRequestRepository()
    payload = RequestPayload(title="Add feature", description="desc", context={})
    request = Request(
        id="req-2",
        tenant_id="tenant",
        source="direct_user",
        sender="user@example.com",
        payload=payload,
        state=RequestState.SPEC_READY,
        metadata={
            "project": {
                "repository": "org/project",
                "branch": "main",
            }
        },
    )
    spec_obj = _StubSpecGenerator().generate(request)
    request.metadata["spec"] = spec_obj.as_dict()
    repo.save(request)
    run_log = _StubRunLog()
    operator = _StubWorkspaceOperator()

    outcome = ExecuteRequest(
        repository=repo,
        workspace_operator=operator,
        run_log=run_log,
    )(request_id="req-2")

    stored = repo.get("req-2")
    assert stored.state == RequestState.PATCH_READY
    assert stored.metadata["workspace"]["mode"] == "docker"
    assert stored.metadata["execution"]["diff"] == "diff"
    assert outcome.diff == "diff"
    assert any(event.get("stage") == "codex" for event in run_log.events if "stage" in event)
    assert operator.prepared and operator.executed and operator.teardown_called
