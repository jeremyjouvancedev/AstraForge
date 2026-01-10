"""Tests for Codex workspace operator helpers."""

from __future__ import annotations

import re
import subprocess

from astraforge.domain.models.workspace import CommandResult, ExecutionOutcome, WorkspaceContext
from astraforge.infrastructure.workspaces.codex import CodexWorkspaceOperator


class _DummyProvisioner:
    def spawn(self, repo: str, toolchain: str) -> str:  # pragma: no cover - test stub
        raise NotImplementedError

    def cleanup(self, ref: str) -> None:  # pragma: no cover - test stub
        raise NotImplementedError


class _StubRunner:
    def __init__(self, result: CommandResult) -> None:
        self._result = result
        self.last_command = None
        self.last_allow_failure = None
        self.commands: list[list[str]] = []

    def run(
        self,
        command,
        *,
        cwd=None,
        env=None,
        stream=None,
        allow_failure=False,
    ) -> CommandResult:
        rendered = list(command)
        self.last_command = rendered
        self.commands.append(rendered)
        self.last_allow_failure = allow_failure
        return self._result


class _CPUStubRunner:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout
        self.commands: list[list[str]] = []
        self.dry_run = False

    def run(
        self,
        command,
        *,
        cwd=None,
        env=None,
        stream=None,
        allow_failure=False,
    ) -> CommandResult:
        rendered = list(command)
        self.commands.append(rendered)
        return CommandResult(exit_code=0, stdout=self.stdout, stderr="")


class _TrackingProvisioner:
    def __init__(self) -> None:
        self.cleaned: list[str] = []

    def spawn(self, repo: str, toolchain: str) -> str:  # pragma: no cover - test stub
        raise NotImplementedError

    def cleanup(self, ref: str) -> None:
        self.cleaned.append(ref)


class _TrackingRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(
        self,
        command,
        *,
        cwd=None,
        env=None,
        stream=None,
        allow_failure=False,
    ) -> CommandResult:
        rendered = list(command)
        self.commands.append(rendered)
        return CommandResult(exit_code=0, stdout="", stderr="")


def test_collect_results_skips_diff_when_workspace_not_git_repo():
    events: list[dict[str, str]] = []

    def stream(event: dict[str, str]) -> None:
        events.append(event)

    runner = _StubRunner(
        CommandResult(
            exit_code=128,
            stdout="fatal: Not a git repository (or any of the parent directories): .git\n",
            stderr="",
        )
    )
    operator = CodexWorkspaceOperator(provisioner=_DummyProvisioner(), runner=runner)
    workspace = WorkspaceContext(
        ref="docker://codex-123",
        mode="docker",
        repository="example/repo",
        branch="main",
        path="/workspace",
    )

    request = type("RequestStub", (), {"id": "req-123", "metadata": {}})()

    outcome = operator._collect_results(request, workspace, stream=stream)

    assert outcome.diff == ""
    diff_events = [event for event in events if event.get("stage") == "diff"]
    assert diff_events
    assert diff_events[-1]["message"] == "Git repository not detected in workspace; skipping diff"
    assert runner.last_allow_failure is True


def test_teardown_skips_when_keep_alive_set(monkeypatch):
    runner = _TrackingRunner()
    provisioner = _TrackingProvisioner()
    operator = CodexWorkspaceOperator(provisioner=provisioner, runner=runner)
    workspace = WorkspaceContext(
        ref="docker://codex-123",
        mode="docker",
        repository="example/repo",
        branch="main",
        path="/workspace",
    )

    monkeypatch.setenv("CODEX_WORKSPACE_KEEP_ALIVE", "1")

    operator.teardown(workspace)

    assert runner.commands == []
    assert provisioner.cleaned == []


class _FallbackRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(
        self,
        command,
        *,
        cwd=None,
        env=None,
        stream=None,
        allow_failure=False,
    ) -> CommandResult:
        rendered = list(command)
        self.commands.append(rendered)
        if "--pull" in rendered:
            raise subprocess.CalledProcessError(125, rendered, output="")
        return CommandResult(exit_code=0, stdout="", stderr="")


class _WorkspaceRunner:
    def __init__(self, contents: dict[str, set[str]] | None = None, git_repos: set[str] | None = None):
        self.contents = contents or {}
        self.git_repos = set(git_repos or set())
        self.commands: list[list[str]] = []

    def _ensure_dir(self, path: str) -> None:
        self.contents.setdefault(path, set())

    def _simulate_ls(self, script: str) -> CommandResult:
        match = re.search(r"ls -A\s+([^|\s]+)", script)
        path = match.group(1) if match else ""
        entries = list(self.contents.get(path, set()))
        if "grep -v '^\\.cache$'" in script:
            entries = [entry for entry in entries if entry != ".cache"]
        stdout = f"{entries[0]}\n" if entries else ""
        return CommandResult(exit_code=0, stdout=stdout, stderr="")

    def run(
        self,
        command,
        *,
        cwd=None,
        env=None,
        stream=None,
        allow_failure=False,
    ) -> CommandResult:
        rendered = list(command)
        self.commands.append(rendered)

        if len(rendered) >= 4 and rendered[:2] == ["git", "-C"] and rendered[3] == "rev-parse":
            path = rendered[2]
            exit_code = 0 if path in self.git_repos else 128
            return CommandResult(exit_code=exit_code, stdout="", stderr="")

        if len(rendered) >= 2 and rendered[0] == "git" and rendered[1] == "clone":
            path = rendered[-1]
            self._ensure_dir(path)
            self.git_repos.add(path)
            return CommandResult(exit_code=0, stdout="", stderr="")

        if rendered[:2] == ["rm", "-rf"] and len(rendered) >= 3:
            target = rendered[2]
            parent = "/".join(target.split("/")[:-1]) or "/"
            name = target.split("/")[-1]
            entries = self.contents.get(parent, set())
            if name in entries:
                entries.remove(name)
                self.contents[parent] = entries
            self.contents.pop(target, None)
            return CommandResult(exit_code=0, stdout="", stderr="")

        if rendered[:2] == ["mkdir", "-p"] and len(rendered) >= 3:
            self._ensure_dir(rendered[2])
            return CommandResult(exit_code=0, stdout="", stderr="")

        if rendered[:2] == ["sh", "-c"] and len(rendered) >= 3:
            return self._simulate_ls(rendered[2])

        return CommandResult(exit_code=0, stdout="", stderr="")


def test_bootstrap_builds_local_image_when_registry_denies(monkeypatch, tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM scratch\n")
    monkeypatch.setenv("CODEX_CLI_BUILD_CONTEXT", str(tmp_path))
    events: list[dict[str, str]] = []

    def stream(event: dict[str, str]) -> None:
        events.append(event)

    runner = _FallbackRunner()
    operator = CodexWorkspaceOperator(provisioner=_DummyProvisioner(), runner=runner)

    operator._bootstrap_docker_container("codex-123", "astraforge/codex-cli:latest", stream)

    assert any("--pull" in cmd for cmd in runner.commands)
    assert any(cmd[:3] == ["docker", "build", "-t"] for cmd in runner.commands)
    assert any(
        cmd[:5] == ["docker", "run", "-d", "--name", "codex-123"] and "--pull" not in cmd
        for cmd in runner.commands
    )
    assert any(
        event.get("message", "").startswith("Image astraforge/codex-cli:latest unavailable")
        for event in events
    )


def test_clone_skips_when_repo_already_present():
    runner = _WorkspaceRunner(contents={"/workspace": {"README.md"}}, git_repos={"/workspace"})
    events: list[dict[str, str]] = []
    operator = CodexWorkspaceOperator(provisioner=_DummyProvisioner(), runner=runner)

    path = operator._clone_repository(
        "local",
        "local",
        {"repository": "example/repo"},
        events.append,
        target_path="/workspace",
    )

    assert path == "/workspace"
    assert not any(cmd[:2] == ["git", "clone"] for cmd in runner.commands)
    assert any("already contains a git repository" in event.get("message", "") for event in events)


def test_clone_cleans_cache_and_uses_root_when_only_cache_present():
    runner = _WorkspaceRunner(contents={"/workspace": {".cache"}})
    events: list[dict[str, str]] = []
    operator = CodexWorkspaceOperator(provisioner=_DummyProvisioner(), runner=runner)

    path = operator._clone_repository(
        "local",
        "local",
        {"repository": "example/repo"},
        events.append,
        target_path="/workspace",
    )

    clone_commands = [cmd for cmd in runner.commands if cmd[:2] == ["git", "clone"]]
    assert path == "/workspace"
    assert any(cmd[:2] == ["rm", "-rf"] for cmd in runner.commands)
    assert clone_commands and clone_commands[0][-1] == "/workspace"
    assert "/workspace" in runner.git_repos


def test_clone_uses_subdirectory_when_workspace_has_files():
    runner = _WorkspaceRunner(contents={"/workspace": {".cache", "notes.txt"}})
    events: list[dict[str, str]] = []
    operator = CodexWorkspaceOperator(provisioner=_DummyProvisioner(), runner=runner)

    path = operator._clone_repository(
        "local",
        "local",
        {"repository": "jeremyjouvancedev/ai-flow"},
        events.append,
        target_path="/workspace",
    )

    clone_commands = [cmd for cmd in runner.commands if cmd[:2] == ["git", "clone"]]
    assert path == "/workspace/ai-flow"
    assert clone_commands and clone_commands[0][-1] == "/workspace/ai-flow"
    assert "/workspace/ai-flow" in runner.git_repos
    assert any("cloning repository into /workspace/ai-flow" in event.get("message", "") for event in events)


def test_clone_uses_github_default_base():
    runner = _WorkspaceRunner()
    events: list[dict[str, str]] = []
    operator = CodexWorkspaceOperator(provisioner=_DummyProvisioner(), runner=runner)

    path = operator._clone_repository(
        "local",
        "local",
        {"repository": "octo/repo", "provider": "github"},
        events.append,
        target_path="/workspace",
    )

    clone_commands = [cmd for cmd in runner.commands if cmd[:2] == ["git", "clone"]]
    assert path == "/workspace"
    assert clone_commands
    assert clone_commands[0][2] == "https://github.com/octo/repo.git"


def test_wrap_exec_includes_namespace_for_k8s():
    operator = CodexWorkspaceOperator(provisioner=_DummyProvisioner())

    command = operator._wrap_exec("astraforge-local/workspace-123", "k8s", ["git", "status"])

    assert command[:5] == ["kubectl", "exec", "-i", "-n", "astraforge-local"]
    assert command[5:] == ["workspace-123", "--", "git", "status"]


def test_codex_command_uses_request_llm_config(monkeypatch):
    operator = CodexWorkspaceOperator(provisioner=_DummyProvisioner())
    payload = type(
        "PayloadStub",
        (),
        {"description": "test request", "title": "title", "attachments": []},
    )()
    request = type(
        "RequestStub",
        (),
        {
            "metadata": {"llm": {"provider": "ollama", "model": "gpt-oss:120b"}},
            "payload": payload,
        },
    )()
    workspace = WorkspaceContext(
        ref="local",
        mode="local",
        repository="example/repo",
        branch="main",
        path="/workspace",
        proxy_url="http://proxy.local",
    )

    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-key")

    command = operator._codex_command(request, workspace)

    assert command[0] == "env"
    assert "LLM_PROVIDER=ollama" in command
    assert "OLLAMA_MODEL=gpt-oss:120b" in command
    assert "CODEX_WRAPPER_DEFAULT_MODEL=gpt-oss:120b" in command
    assert "OLLAMA_API_KEY=ollama-key" in command
    assert not any("auth.api_key" in part for part in command)


def test_codex_command_defaults_ollama_api_key(monkeypatch):
    operator = CodexWorkspaceOperator(provisioner=_DummyProvisioner())
    payload = type(
        "PayloadStub",
        (),
        {"description": "test request", "title": "title", "attachments": []},
    )()
    request = type(
        "RequestStub",
        (),
        {
            "metadata": {"llm": {"provider": "ollama", "model": "gpt-oss:20b"}},
            "payload": payload,
        },
    )()
    workspace = WorkspaceContext(
        ref="local",
        mode="local",
        repository="example/repo",
        branch="main",
        path="/workspace",
        proxy_url="http://proxy.local",
    )

    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)

    command = operator._codex_command(request, workspace)

    assert "OLLAMA_API_KEY=local" in command


def test_sample_cpu_usage_seconds_from_docker():
    payload = "__PATH:/sys/fs/cgroup/cpu.stat__\nusage_usec 1250000\nuser_usec 1000000\nsystem_usec 250000\n"
    runner = _CPUStubRunner(payload)
    operator = CodexWorkspaceOperator(provisioner=_DummyProvisioner(), runner=runner)
    workspace = WorkspaceContext(
        ref="docker://codex-123",
        mode="docker",
        repository="example/repo",
        branch="main",
        path="/workspace",
        metadata={"container": "codex-123"},
    )

    seconds = operator._sample_cpu_usage_seconds(workspace)

    assert seconds == 1.25
    assert runner.commands
    assert runner.commands[-1][:4] == ["docker", "exec", "codex-123", "sh"]


def test_sample_cpu_usage_seconds_from_k8s():
    payload = "__PATH:/sys/fs/cgroup/cpuacct/cpuacct.usage__\n2000000000\n"
    runner = _CPUStubRunner(payload)
    operator = CodexWorkspaceOperator(provisioner=_DummyProvisioner(), runner=runner)
    workspace = WorkspaceContext(
        ref="k8s://astraforge/workspace-123",
        mode="k8s",
        repository="example/repo",
        branch="main",
        path="/workspace",
    )

    seconds = operator._sample_cpu_usage_seconds(workspace)

    assert seconds == 2.0
    assert runner.commands
    assert runner.commands[-1][:5] == ["kubectl", "exec", "-n", "astraforge", "workspace-123"]


def test_run_codex_includes_cpu_seconds_in_reports(monkeypatch):
    operator = CodexWorkspaceOperator(provisioner=_DummyProvisioner())
    request = type("RequestStub", (), {"id": "req-123", "metadata": {}})()
    workspace = WorkspaceContext(
        ref="docker://codex-123",
        mode="docker",
        repository="example/repo",
        branch="main",
        path="/workspace",
        metadata={"container": "codex-123"},
    )

    monkeypatch.setattr(
        operator,
        "_codex_command",
        lambda *args, **kwargs: ["codex", "exec"],
    )
    monkeypatch.setattr(
        operator,
        "_exec",
        lambda *args, **kwargs: CommandResult(exit_code=0, stdout="ok", stderr=""),
    )
    expected_outcome = ExecutionOutcome(diff="diff", artifacts={}, reports={})
    monkeypatch.setattr(
        operator,
        "_collect_results",
        lambda *args, **kwargs: expected_outcome,
    )
    monkeypatch.setattr(
        operator,
        "_sample_cpu_usage_seconds",
        lambda *args, **kwargs: 7.5,
    )

    outcome = operator.run_agent(request, workspace, stream=lambda event: None)

    assert outcome.reports["codex_cpu_seconds"] == 7.5
    assert "codex_exit_code" in outcome.reports
    assert "codex_stdout" in outcome.reports


def test_run_agent_records_runtime_in_quota_service(monkeypatch):
    operator = CodexWorkspaceOperator(provisioner=_DummyProvisioner())
    request = type("RequestStub", (), {"id": "req-123", "metadata": {}, "tenant_id": "workspace-uid"})()
    workspace = WorkspaceContext(
        ref="docker://codex-123",
        mode="docker",
        repository="example/repo",
        branch="main",
        path="/workspace",
        metadata={"container": "codex-123"},
    )

    monkeypatch.setattr(operator, "_codex_command", lambda *args, **kwargs: ["codex", "exec"])
    monkeypatch.setattr(
        operator,
        "_exec",
        lambda *args, **kwargs: CommandResult(exit_code=0, stdout="ok", stderr=""),
    )
    monkeypatch.setattr(
        operator,
        "_collect_results",
        lambda *args, **kwargs: ExecutionOutcome(diff="", artifacts={}, reports={}),
    )
    monkeypatch.setattr(operator, "_sample_cpu_usage_seconds", lambda *args, **kwargs: 4.2)

    workspace_model = type("WorkspaceStub", (), {"uid": "workspace-uid"})()
    monkeypatch.setattr(operator, "_workspace_for_request", lambda *_: workspace_model)

    recorded: dict[str, tuple[object, float]] = {}

    class _Quota:
        def record_sandbox_runtime(self, ws, seconds):
            recorded["call"] = (ws, seconds)

    monkeypatch.setattr(operator, "_quota_service", lambda: _Quota())

    operator.run_agent(request, workspace, stream=lambda event: None)

    assert recorded["call"][0] is workspace_model
    assert recorded["call"][1] == 4.2
