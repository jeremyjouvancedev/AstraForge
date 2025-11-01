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
            "prompt": "Stabilize the integration suite by adding retries.",
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
    captured: dict[str, object] = {}

    class _RunLogStub:
        def __init__(self):
            self.events: list[dict[str, object]] = []

        def publish(self, request_id: str, event: dict[str, object]) -> None:
            self.events.append(event)

    run_log = _RunLogStub()

    def fake_delay(request_id: str, *_, **__):
        captured["id"] = request_id

    monkeypatch.setattr(
        "astraforge.interfaces.rest.views.container.resolve_run_log",
        lambda: run_log,
    )
    monkeypatch.setattr(
        "astraforge.interfaces.rest.views.app_tasks.execute_request_task.delay",
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
    assert payload["payload"]["title"] == "Stabilize the integration suite by adding retries."
    assert payload["payload"]["description"] == body["prompt"]
    assert payload["metadata"]["prompt"] == body["prompt"]
    assert payload["project"]["id"] == str(link.id)
    assert payload["state"] == "RECEIVED"
    assert payload["metadata"]["project"]["repository"] == "org/project"
    assert payload["metadata"].get("spec") is None
    assert captured.get("id") == payload["id"]
    assert run_log.events and run_log.events[0]["message"] == body["prompt"]
    assert run_log.events[0]["type"] == "user_prompt"
    assert run_log.events[0]["request_id"] == payload["id"]


def test_create_request_preserves_description_whitespace(api_client, user, request_payload, monkeypatch):
    RepositoryLink.objects.create(
        user=user,
        provider=RepositoryLink.Provider.GITLAB,
        repository="org/project",
        access_token="token-123",
    )
    link = RepositoryLink.objects.get(user=user)

    monkeypatch.setattr(
        "astraforge.interfaces.rest.views.app_tasks.execute_request_task.delay",
        lambda request_id, *_, **__: None,
    )

    body = request_payload(link.id)
    raw_description = "   Improve build pipeline?\n\nAdd caching please.   "
    body["prompt"] = raw_description

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
            metadata={"feature_branch": f"astraforge/{request.id}"},
        )

    def run_codex(self, request: Request, spec: DevelopmentSpec, workspace: WorkspaceContext, *, stream):
        self.executed = True
        stream({"type": "status", "stage": "codex", "message": "running"})
        return ExecutionOutcome(diff="diff", artifacts={"branch": f"astraforge/{request.id}"})

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
        state=RequestState.RECEIVED,
        metadata={
            "project": {
                "repository": "org/project",
                "branch": "main",
            }
        },
    )
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
    assert stored.metadata["spec"]["summary"] == "desc"
    assert stored.metadata["spec"]["implementation_steps"] == ["desc"]
    assert stored.metadata["workspace"]["mode"] == "docker"
    assert stored.metadata["execution"]["diff"] == "diff"
    assert stored.metadata.get("history_jsonl") == "[]"
    assert outcome.diff == "diff"
    assert any(event.get("stage") == "codex" for event in run_log.events if "stage" in event)
    assert operator.prepared and operator.executed and operator.teardown_called
    runs_meta = stored.metadata.get("runs")
    assert runs_meta and len(runs_meta) == 1
    run_entry = runs_meta[0]
    assert run_entry["status"] == "completed"
    assert run_entry["diff"] == "diff"
    assert run_entry["events"]
    assert all(event.get("run_id") == run_entry["id"] for event in run_entry["events"])
    assert run_entry["artifacts"]["branch"].startswith("astraforge/")
    assert run_entry["artifacts"]["history"] == "[]"


def test_run_viewset_returns_run_history(api_client, user, monkeypatch):
    repo = InMemoryRequestRepository()
    monkeypatch.setattr("astraforge.bootstrap.repository", repo, raising=False)
    monkeypatch.setattr("astraforge.interfaces.rest.views.repository", repo, raising=False)

    payload = RequestPayload(title="Add feature", description="desc", context={})
    request = Request(
        id="req-api-run",
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
    operator = _StubWorkspaceOperator()

    ExecuteRequest(
        repository=repo,
        workspace_operator=operator,
        run_log=run_log,
    )(request_id="req-api-run")

    run_list = api_client.get(reverse("run-list"))
    assert run_list.status_code == 200
    runs = run_list.json()
    assert any(item["request_id"] == "req-api-run" for item in runs)

    run_entry = repo.get("req-api-run").metadata["runs"][0]
    detail = api_client.get(reverse("run-detail", args=[run_entry["id"]]))
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["diff"] == "diff"
    assert payload["events"]
    assert payload["diff_size"] == len("diff")
    assert payload["artifacts"]["history"] == "[]"
    assert payload["artifacts"]["branch"].startswith("astraforge/")
    assert payload["artifacts"]["branch"].startswith("astraforge/")


def test_run_viewset_falls_back_to_execution_metadata(api_client, user, monkeypatch):
    repo = InMemoryRequestRepository()
    monkeypatch.setattr("astraforge.bootstrap.repository", repo, raising=False)
    monkeypatch.setattr("astraforge.interfaces.rest.views.repository", repo, raising=False)

    payload = RequestPayload(title="Legacy run", description="desc", context={})
    request = Request(
        id="req-fallback-run",
        tenant_id="tenant",
        source="direct_user",
        sender="user@example.com",
        payload=payload,
        metadata={
            "project": {"repository": "org/project", "branch": "main"},
            "execution": {
                "diff": "diff",
                "reports": {"status": "completed"},
            },
        },
    )
    repo.save(request)

    run_list = api_client.get(reverse("run-list"))
    assert run_list.status_code == 200
    runs = run_list.json()
    assert any(item["request_id"] == "req-fallback-run" for item in runs)

    fallback_id = next(item["id"] for item in runs if item["request_id"] == "req-fallback-run")
    detail = api_client.get(reverse("run-detail", args=[fallback_id]))
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["diff"] == "diff"
    assert payload["events"]
    assert payload["reports"] == {"status": "completed"}
    assert payload.get("artifacts") in ({}, None) or "branch" not in payload.get("artifacts", {})
    assert payload["events"][0]["request_id"] == "req-fallback-run"
    assert payload["events"][0]["run_id"] == fallback_id
    stages = {event.get("stage") for event in payload["events"]}
    assert "diff" in stages


def test_merge_request_viewset_returns_merge_requests(api_client, user, monkeypatch):
    repo = InMemoryRequestRepository()
    monkeypatch.setattr("astraforge.bootstrap.repository", repo, raising=False)
    monkeypatch.setattr("astraforge.interfaces.rest.views.repository", repo, raising=False)

    payload = RequestPayload(title="Add feature", description="desc", context={})
    request = Request(
        id="req-api-mr",
        tenant_id="tenant",
        source="direct_user",
        sender="user@example.com",
        payload=payload,
        metadata={
            "project": {"repository": "org/project", "branch": "main"},
            "execution": {"diff": "diff"},
            "mr": {
                "id": "mr-1",
                "ref": "https://gitlab.example.com/mr/1",
                "title": "Add feature",
                "description": "Details",
                "target_branch": "main",
                "source_branch": "feature/add",
                "status": "OPEN",
            },
        },
    )
    repo.save(request)

    response = api_client.get(reverse("merge-request-list"))
    assert response.status_code == 200
    payload = response.json()
    assert any(item["id"] == "mr-1" for item in payload)

    detail = api_client.get(reverse("merge-request-detail", args=["mr-1"]))
    assert detail.status_code == 200
    mr_payload = detail.json()
    assert mr_payload["diff"] == "diff"
    assert mr_payload["target_branch"] == "main"
