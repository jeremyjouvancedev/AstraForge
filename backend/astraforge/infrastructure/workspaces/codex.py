"""Workspace operator that provisions Codex CLI environments and runs them."""

from __future__ import annotations

import base64
import json
import logging
import os
import shlex
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Tuple

from astraforge.domain.models.request import Request
from astraforge.domain.models.spec import DevelopmentSpec
from astraforge.domain.models.workspace import CommandResult, ExecutionOutcome, WorkspaceContext
from astraforge.domain.providers.interfaces import Provisioner, WorkspaceOperator

logger = logging.getLogger(__name__)


@dataclass
class CommandRunner:
    """Utility for executing shell commands with optional streaming."""

    dry_run: bool = True

    def run(
        self,
        command: Iterable[str],
        *,
        cwd: str | None = None,
        env: Dict[str, str] | None = None,
        stream: Callable[[dict[str, Any]], None] | None = None,
        allow_failure: bool = False,
    ) -> CommandResult:
        args = list(command)
        rendered = " ".join(shlex.quote(arg) for arg in args)
        if stream is not None:
            stream({"type": "command", "command": rendered, "cwd": cwd})
        logger.debug("Executing command", extra={"command": args, "cwd": cwd, "dry_run": self.dry_run})
        if self.dry_run:
            return CommandResult(exit_code=0, stdout="", stderr="")
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
        process = subprocess.Popen(
            args,
            cwd=cwd,
            env=process_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        output_lines: List[str] = []
        assert process.stdout is not None
        for line in process.stdout:
            output_lines.append(line)
            if stream is not None:
                stream({"type": "log", "message": line.rstrip("\n")})
        process.wait()
        stdout = "".join(output_lines)
        if process.returncode != 0 and not allow_failure:
            error_payload = {
                "type": "error",
                "message": f"Command '{rendered}' failed with exit code {process.returncode}",
                "output": stdout.strip(),
                "exit_code": process.returncode,
            }
            if stream is not None:
                stream(error_payload)
            logger.error(
                "Command failed",
                extra={"command": args, "cwd": cwd, "exit_code": process.returncode, "stdout": stdout},
            )
            raise subprocess.CalledProcessError(process.returncode, args, output=stdout)
        logger.debug(
            "Command completed",
            extra={"command": args, "cwd": cwd, "exit_code": process.returncode, "stdout": stdout[:500]},
        )
        return CommandResult(exit_code=process.returncode, stdout=stdout, stderr="")


def _should_execute_commands() -> bool:
    return os.getenv("ASTRAFORGE_EXECUTE_COMMANDS", "0").lower() in {
        "1",
        "true",
        "yes",
    }


@dataclass
class CodexWorkspaceOperator(WorkspaceOperator):
    """Coordinates provisioning, proxy bootstrap, and Codex CLI execution."""

    provisioner: Provisioner
    proxy_base_port: int = 5200
    image: str | None = None
    runner: CommandRunner = field(default_factory=lambda: CommandRunner(dry_run=not _should_execute_commands()))

    def prepare(
        self,
        request: Request,
        spec: DevelopmentSpec,
        *,
        stream: Callable[[dict[str, Any]], None],
    ) -> WorkspaceContext:
        project = request.metadata.get("project", {})
        repo_slug = project.get("repository", "unknown-repo")
        branch = project.get("branch", "main")
        workspace_ref = self.provisioner.spawn(repo=repo_slug.replace("/", "-"), toolchain="codex")
        mode, identifier = self._parse_ref(workspace_ref)
        image = self.image or getattr(self.provisioner, "image", "astraforge/codex-cli:latest")
        stream(
            {
                "type": "status",
                "stage": "provisioning",
                "message": f"Provisioned {mode} workspace {identifier} with image {image}",
            }
        )
        if mode == "docker":
            self._bootstrap_docker_container(identifier, image, stream)
        proxy_url = self._ensure_proxy(identifier, mode, stream)
        workspace_path = "/workspace" if mode == "docker" else f"/workspaces/{identifier}"
        self._clone_repository(identifier, mode, project, stream, target_path=workspace_path)
        self._write_spec_file(identifier, mode, spec, stream, workspace_path)
        return WorkspaceContext(
            ref=workspace_ref,
            mode=mode,
            repository=repo_slug,
            branch=branch,
            path=workspace_path,
            proxy_url=proxy_url,
            metadata={"container": identifier, "image": image},
        )

    def run_codex(
        self,
        request: Request,
        spec: DevelopmentSpec,
        workspace: WorkspaceContext,
        *,
        stream: Callable[[dict[str, Any]], None],
    ) -> ExecutionOutcome:
        command = self._codex_command(workspace)
        stream(
            {
                "type": "status",
                "stage": "codex",
                "message": "Starting Codex CLI session",
            }
        )
        result = self._exec(workspace, command, stream=stream, allow_failure=True)
        outcome = self._collect_results(workspace, stream)
        outcome.reports.setdefault("codex_exit_code", result.exit_code)
        outcome.reports.setdefault("codex_stdout", result.stdout[:4000])
        return outcome

    def teardown(self, workspace: WorkspaceContext) -> None:
        mode, identifier = self._parse_ref(workspace.ref)
        if mode == "docker":
            self.runner.run(
                ["docker", "rm", "-f", identifier],
                stream=lambda event: None,
                allow_failure=True,
            )
        self.provisioner.cleanup(workspace.ref)

    # internal helpers -------------------------------------------------

    def _parse_ref(self, ref: str) -> Tuple[str, str]:
        if "://" in ref:
            mode, identifier = ref.split("://", 1)
        else:
            mode, identifier = getattr(self.provisioner, "name", "workspace"), ref
        return mode, identifier

    def _bootstrap_docker_container(
        self,
        container_name: str,
        image: str,
        stream: Callable[[dict[str, Any]], None],
    ) -> None:
        self.runner.run(
            ["docker", "rm", "-f", container_name],
            stream=stream,
            allow_failure=True,
        )
        pull_command = [
            "docker",
            "run",
            "-d",
            "--pull",
            "always",
            "--name",
            container_name,
            image,
            "sleep",
            "infinity",
        ]
        try:
            self.runner.run(pull_command, stream=stream)
        except subprocess.CalledProcessError as exc:
            output_text = (exc.output or "").lower()
            should_fallback = any(
                phrase in output_text
                for phrase in (
                    "pull access denied",
                    "repository does not exist",
                    "not found",
                )
            ) or exc.returncode == 125
            if should_fallback:
                stream(
                    {
                        "type": "status",
                        "stage": "workspace",
                        "message": (
                            f"Image {image} unavailable from registry; attempting local build"
                        ),
                    }
                )
                self._ensure_local_image(image, stream)
                run_command = [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    container_name,
                    image,
                    "sleep",
                    "infinity",
                ]
                self.runner.run(run_command, stream=stream)
            else:
                raise
        stream(
            {
                "type": "status",
                "stage": "workspace",
                "message": f"Workspace container {container_name} is running",
            }
        )

    def _ensure_proxy(
        self,
        identifier: str,
        mode: str,
        stream: Callable[[dict[str, Any]], None],
    ) -> str:
        port = self.proxy_base_port + (hash(identifier) % 2000)
        if mode == "docker":
            command = [
                "docker",
                "exec",
                identifier,
                "nohup",
                "codex-proxy",
                "--listen",
                f"0.0.0.0:{port}",
            ]
        else:
            command = [
                "kubectl",
                "exec",
                identifier,
                "--",
                "codex-proxy",
                "--listen",
                f"0.0.0.0:{port}",
            ]
        self.runner.run(command, stream=stream, allow_failure=True)
        proxy_url = f"http://localhost:{port}"
        stream(
            {
                "type": "status",
                "stage": "proxy",
                "message": f"LLM proxy available at {proxy_url}",
            }
        )
        return proxy_url

    def _clone_repository(
        self,
        identifier: str,
        mode: str,
        project: Dict[str, Any],
        stream: Callable[[dict[str, Any]], None],
        *,
        target_path: str,
    ) -> None:
        base_url = project.get("base_url") or "https://gitlab.com"
        repository = project.get("repository", "")
        repo_url = f"{base_url}/{repository}.git" if repository else base_url
        command = self._wrap_exec(identifier, mode, ["git", "clone", repo_url, target_path])
        self.runner.run(command, stream=stream, allow_failure=True)
        stream(
            {
                "type": "status",
                "stage": "clone",
                "message": f"Repository clone initiated from {repo_url}",
            }
        )

    def _write_spec_file(
        self,
        identifier: str,
        mode: str,
        spec: DevelopmentSpec,
        stream: Callable[[dict[str, Any]], None],
        workspace_path: str,
    ) -> None:
        payload = spec.as_dict()
        json_payload = json.dumps(payload, ensure_ascii=False)
        encoded = base64.b64encode(json_payload.encode("utf-8")).decode("ascii")
        destination = f"{workspace_path}/.codex/spec.json"
        script = (
            f"mkdir -p {workspace_path}/.codex && "
            f"echo '{encoded}' | base64 -d > {destination}"
        )
        command = self._wrap_exec(identifier, mode, ["sh", "-c", script])
        self.runner.run(command, stream=stream, allow_failure=True)
        stream(
            {
                "type": "status",
                "stage": "spec",
                "message": f"Spec uploaded to {destination}",
            }
        )

    def _codex_command(self, workspace: WorkspaceContext) -> List[str]:
        base = ["codex", "--spec", f"{workspace.path}/.codex/spec.json"]
        return self._wrap_exec(workspace.metadata.get("container", workspace.ref), workspace.mode, base)

    def _wrap_exec(self, identifier: str, mode: str, command: List[str]) -> List[str]:
        if mode == "docker":
            return ["docker", "exec", identifier, *command]
        if mode == "k8s":
            return ["kubectl", "exec", identifier, "--", *command]
        return command

    def _exec(
        self,
        workspace: WorkspaceContext,
        command: List[str],
        *,
        stream: Callable[[dict[str, Any]], None],
        allow_failure: bool = False,
    ) -> CommandResult:
        return self.runner.run(command, stream=stream, allow_failure=allow_failure)

    def _collect_results(
        self,
        workspace: WorkspaceContext,
        stream: Callable[[dict[str, Any]], None],
    ) -> ExecutionOutcome:
        diff_command = self._wrap_exec(
            workspace.metadata.get("container", workspace.ref),
            workspace.mode,
            ["git", "-C", workspace.path, "diff"],
        )
        result = self.runner.run(diff_command, stream=stream, allow_failure=True)
        stdout_lower = (result.stdout or "").lower()
        diff_output = result.stdout
        if result.exit_code != 0 and "not a git repository" in stdout_lower:
            diff_output = ""
            status_message = "Git repository not detected in workspace; skipping diff"
        elif result.exit_code != 0:
            status_message = "Workspace diff command failed; review logs for details"
        else:
            status_message = "Collected workspace diff"
        stream(
            {
                "type": "status",
                "stage": "diff",
                "message": status_message,
            }
        )
        return ExecutionOutcome(diff=diff_output)

    def _ensure_local_image(
        self,
        image: str,
        stream: Callable[[dict[str, Any]], None],
    ) -> None:
        context_override = os.getenv("CODEX_CLI_BUILD_CONTEXT")
        if context_override:
            build_context = Path(context_override)
        else:
            backend_root = Path(__file__).resolve().parents[3]
            build_context = backend_root / "codex_cli_stub"
        if not build_context.exists():
            stream(
                {
                    "type": "error",
                    "stage": "workspace",
                    "message": (
                        f"Local Codex CLI build context missing at {build_context}; "
                        "aborting workspace bootstrap"
                    ),
                }
            )
            raise FileNotFoundError(f"Codex CLI build context not found: {build_context}")
        self.runner.run(
            ["docker", "build", "-t", image, str(build_context)],
            stream=stream,
        )
        stream(
            {
                "type": "status",
                "stage": "workspace",
                "message": f"Built local Codex CLI image from {build_context}",
            }
        )

def from_env(provisioner: Provisioner) -> CodexWorkspaceOperator:
    image = getattr(provisioner, "image", None)
    return CodexWorkspaceOperator(provisioner=provisioner, image=image)
