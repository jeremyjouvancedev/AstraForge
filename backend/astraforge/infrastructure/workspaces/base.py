"Base workspace operator for running SWE agents in provisioned environments."

from __future__ import annotations

import base64
import json
import logging
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Tuple, TYPE_CHECKING
from urllib.parse import quote, urlparse, urlunparse

from astraforge.domain.models.request import Request
from astraforge.domain.models.workspace import CommandResult, ExecutionOutcome, WorkspaceContext
from astraforge.domain.providers.interfaces import Provisioner, WorkspaceOperator
from astraforge.infrastructure.cpu_usage import build_cpu_probe_script, parse_cpu_usage_payload

if TYPE_CHECKING:  # pragma: no cover - typing only
    from astraforge.accounts.models import Workspace
    from astraforge.quotas.services import WorkspaceQuotaService

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


def _should_skip_image_pull() -> bool:
    # Use generic skip pull env or agent specific if needed
    value = os.getenv("ASTRAFORGE_WORKSPACE_SKIP_PULL") or os.getenv("CODEX_CLI_SKIP_PULL", "")
    return value.lower() in {"1", "true", "yes"}


def _should_keep_workspace_alive() -> bool:
    value = os.getenv("ASTRAFORGE_WORKSPACE_KEEP_ALIVE") or os.getenv("CODEX_WORKSPACE_KEEP_ALIVE", "")
    return value.lower() in {"1", "true", "yes"}


@dataclass
class BaseAgentWorkspaceOperator(WorkspaceOperator):
    """Base class for workspace operators that run SWE agents."""

    provisioner: Provisioner
    agent_name: str
    toolchain: str
    default_image: str
    config_dir: str = ".astraforge"
    proxy_base_port: int = 5200
    image: str | None = None
    runner: CommandRunner = field(default_factory=lambda: CommandRunner(dry_run=not _should_execute_commands()))
    skip_image_pull: bool = field(default_factory=_should_skip_image_pull)

    def prepare(
        self,
        request: Request,
        *,
        stream: Callable[[dict[str, Any]], None],
    ) -> WorkspaceContext:
        project = request.metadata.get("project", {})
        repo_slug = project.get("repository", "unknown-repo")
        branch = project.get("branch", "main")
        feature_branch = f"astraforge/{request.id}"
        workspace_ref = self.provisioner.spawn(repo=repo_slug.replace("/", "-"), toolchain=self.toolchain)
        mode, identifier = self._parse_ref(workspace_ref)
        image = self.image or getattr(self.provisioner, "image", self.default_image)
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
        workspace_path = self._workspace_path(identifier, mode)
        self._ensure_workspace_directory(identifier, mode, workspace_path, stream)
        workspace_path = self._clone_repository(identifier, mode, project, stream, target_path=workspace_path)
        self._create_feature_branch(
            identifier=identifier,
            mode=mode,
            workspace_path=workspace_path,
            branch=feature_branch,
            stream=stream,
        )
        self._restore_history_from_metadata(
            identifier=identifier,
            mode=mode,
            workspace_path=workspace_path,
            history_content=request.metadata.get("history_jsonl"),
            stream=stream,
        )
        return WorkspaceContext(
            ref=workspace_ref,
            mode=mode,
            repository=repo_slug,
            branch=branch,
            path=workspace_path,
            proxy_url=proxy_url,
            metadata={
                "container": identifier,
                "image": image,
                "feature_branch": feature_branch,
                "base_branch": branch,
            },
        )

    def run_agent(
        self,
        request: Request,
        workspace: WorkspaceContext,
        *,
        stream: Callable[[dict[str, Any]], None],
    ) -> ExecutionOutcome:
        command = self._agent_command(request, workspace)
        stream(
            {
                "type": "status",
                "stage": self.agent_name,
                "message": f"Starting {self.agent_name.title()} session",
            }
        )
        result = self._exec(workspace, command, stream=stream, allow_failure=True)
        runtime_workspace = self._workspace_for_request(request)
        quota_service = self._quota_service()
        outcome = self._collect_results(request, workspace, stream)
        outcome.reports.setdefault(f"{self.agent_name}_exit_code", result.exit_code)
        outcome.reports.setdefault(f"{self.agent_name}_stdout", result.stdout[:4000])
        cpu_seconds = self._sample_cpu_usage_seconds(workspace)
        if cpu_seconds is not None:
            runtime = max(0.0, cpu_seconds)
            outcome.reports.setdefault(f"{self.agent_name}_cpu_seconds", runtime)
            if runtime_workspace is not None and runtime > 0 and quota_service is not None:
                try:
                    quota_service.record_sandbox_runtime(runtime_workspace, runtime)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Failed to record %s runtime for workspace %s: %s",
                        self.agent_name.title(),
                        runtime_workspace.uid,
                        exc,
                    )
        return outcome

    def teardown(self, workspace: WorkspaceContext) -> None:
        if _should_keep_workspace_alive():
            logger.info(
                "Skipping %s workspace teardown",
                self.agent_name.title(),
                extra={"workspace_ref": workspace.ref},
            )
            return
        mode, identifier = self._parse_ref(workspace.ref)
        if mode == "docker":
            self.runner.run(
                ["docker", "rm", "-f", identifier],
                stream=lambda event: None,
                allow_failure=True,
            )
        self.provisioner.cleanup(workspace.ref)

    # methods to be implemented by subclasses --------------------------

    def _agent_command(
        self,
        request: Request,
        workspace: WorkspaceContext,
    ) -> List[str]:
        """Generate the CLI command to run the agent."""
        raise NotImplementedError

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
        network = os.getenv("ASTRAFORGE_WORKSPACE_NETWORK") or os.getenv("CODEX_WORKSPACE_NETWORK")
        self.runner.run(
            ["docker", "rm", "-f", container_name],
            stream=stream,
            allow_failure=True,
        )
        if self.skip_image_pull:
            stream(
                {
                    "type": "status",
                    "stage": "workspace",
                    "message": f"Skipping remote image pull; using local {self.agent_name} image",
                }
            )

        def run_container(selected_network: str | None, include_pull: bool) -> None:
            command = [
                "docker",
                "run",
                "-d",
                "--name",
                container_name,
                *(["--network", selected_network] if selected_network else []),
                *(["--pull", "always"] if include_pull else []),
                "--add-host",
                "host.docker.internal:host-gateway",
                image,
                "sleep",
                "infinity",
            ]
            self.runner.run(command, stream=stream)

        def run_with_image_fallback(selected_network: str | None) -> bool:
            try:
                run_container(selected_network, include_pull=not self.skip_image_pull)
                return True
            except subprocess.CalledProcessError as exc:
                self.runner.run(["docker", "rm", "-f", container_name], allow_failure=True)
                output_text = (exc.output or "").lower()
                network_missing = bool(selected_network) and (
                    "no such network" in output_text
                    or ("network" in output_text and "not found" in output_text)
                )
                if network_missing:
                    return False
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
                    run_container(selected_network, include_pull=False)
                    return True
                raise

        if not run_with_image_fallback(network):
            stream(
                {
                    "type": "status",
                    "stage": "workspace",
                    "message": f"Workspace network {network} not found; falling back to default bridge",
                }
            )
            run_with_image_fallback(None)
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
        network = os.getenv("ASTRAFORGE_WORKSPACE_NETWORK") or os.getenv("CODEX_WORKSPACE_NETWORK")
        default_proxy = "http://llm-proxy:8080" if network else "http://host.docker.internal:18080"
        external_proxy = (
            os.getenv("ASTRAFORGE_WORKSPACE_PROXY_URL")
            or os.getenv("CODEX_WORKSPACE_PROXY_URL")
            or os.getenv("LLM_PROXY_URL")
            or default_proxy
        )
        if external_proxy and external_proxy.lower() != "local":
            stream(
                {
                    "type": "status",
                    "stage": "proxy",
                    "message": f"Using external LLM proxy at {external_proxy}",
                }
            )
            return external_proxy
        port = self.proxy_base_port + (hash(identifier) % 2000)
        # Assuming the image has a proxy or we use a sidecar. 
        # For now, keeping the logic that assumes 'codex-proxy' is available in the image.
        # This might need to be more generic if other agents don't use the same proxy.
        proxy_cmd = os.getenv("ASTRAFORGE_PROXY_COMMAND", "codex-proxy")
        if mode == "docker":
            command = [
                "docker",
                "exec",
                identifier,
                "nohup",
                proxy_cmd,
                "--listen",
                f"0.0.0.0:{port}",
            ]
        else:
            namespace, pod = self._split_k8s_identifier(identifier)
            command = ["kubectl", "exec"]
            if namespace:
                command.extend(["-n", namespace])
            command.extend(
                [
                    pod,
                    "--",
                    "nohup",
                    proxy_cmd,
                    "--listen",
                    f"0.0.0.0:{port}",
                ]
            )
        self.runner.run(command, stream=stream, allow_failure=False)
        proxy_url = f"http://localhost:{port}"
        stream(
            {
                "type": "status",
                "stage": "proxy",
                "message": f"LLM proxy available at {proxy_url}",
            }
        )
        return proxy_url

    def _workspace_has_repo(
        self,
        identifier: str,
        mode: str,
        path: str,
        stream: Callable[[dict[str, Any]], None] | None = None,
    ) -> bool:
        command = self._wrap_exec(
            identifier,
            mode,
            ["git", "-C", path, "rev-parse", "--is-inside-work-tree"],
        )
        result = self.runner.run(command, stream=stream, allow_failure=True)
        return result.exit_code == 0

    def _workspace_has_content(
        self,
        identifier: str,
        mode: str,
        path: str,
        *,
        ignore_cache: bool = False,
        stream: Callable[[dict[str, Any]], None] | None = None,
    ) -> bool:
        path_quoted = shlex.quote(path)
        script_parts = [f"ls -A {path_quoted} 2>/dev/null"]
        if ignore_cache:
            script_parts.append("grep -v '^\.cache$'")
        script_parts.append("head -1")
        script = " | ".join(script_parts)
        command = self._wrap_exec(identifier, mode, ["sh", "-c", script])
        result = self.runner.run(command, stream=stream, allow_failure=True)
        return bool((result.stdout or "").strip())

    def _repository_dirname(self, repository: str) -> str:
        repo_name = repository.rstrip("/").split("/")[-1] or "repo"
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]
        return repo_name or "repo"

    def _clone_repository(
        self,
        identifier: str,
        mode: str,
        project: Dict[str, Any],
        stream: Callable[[dict[str, Any]], None],
        *,
        target_path: str,
    ) -> str:
        repository = (project.get("repository") or "").strip()
        provider = (project.get("provider") or "").lower()
        access_token = project.get("access_token") or project.get("token")
        default_base = "https://github.com" if provider == "github" else "https://gitlab.com"
        base_url = (project.get("base_url") or default_base).rstrip("/")
        if not access_token and project.get("id"):
            try:
                from astraforge.integrations.models import RepositoryLink
                link = RepositoryLink.objects.filter(id=project["id"]).first()
                if link and link.access_token:
                    access_token = link.access_token
                    provider = provider or link.provider.lower()
                    base_override = link.effective_base_url()
                    if base_override:
                        base_url = base_override.rstrip("/")
            except Exception:
                pass

        if repository.startswith(("http://", "https://")):
            repo_url = repository if repository.endswith(".git") else f"{repository}.git"
        elif repository:
            suffix = "" if repository.endswith(".git") else ".git"
            repo_url = f"{base_url}/{repository}{suffix}"
        else:
            repo_url = base_url

        safe_token = None
        redacted_repo_url = repo_url
        if access_token:
            parsed = urlparse(repo_url)
            safe_token = quote(access_token, safe="")
            username = "oauth2" if provider == "gitlab" else "x-access-token"
            authed_netloc = f"{username}:{safe_token}@{parsed.netloc}"
            repo_url = urlunparse(parsed._replace(netloc=authed_netloc))
            redacted_repo_url = urlunparse(parsed._replace(netloc=f"{username}:****@{parsed.netloc}"))

        if self._workspace_has_repo(identifier, mode, target_path, stream=stream):
            stream(
                {
                    "type": "status",
                    "stage": "clone",
                    "message": f"Workspace at {target_path} already contains a git repository; skipping clone",
                }
            )
            return target_path

        target_root = target_path.rstrip("/") or "/"
        has_non_cache_content = self._workspace_has_content(
            identifier, mode, target_root, ignore_cache=True, stream=stream
        )
        if not has_non_cache_content:
            self.runner.run(
                self._wrap_exec(identifier, mode, ["rm", "-rf", f"{target_root}/.cache"]),
                stream=stream,
                allow_failure=True,
            )
        has_any_content = self._workspace_has_content(
            identifier, mode, target_root, ignore_cache=False, stream=stream
        )

        clone_path = target_root
        if has_any_content:
            clone_path = f"{target_root}/{self._repository_dirname(repository)}"
            if self._workspace_has_repo(identifier, mode, clone_path, stream=stream):
                stream(
                    {
                        "type": "status",
                        "stage": "clone",
                        "message": f"Reusing existing repository at {clone_path}",
                    }
                )
                return clone_path
            self.runner.run(
                self._wrap_exec(identifier, mode, ["mkdir", "-p", clone_path]),
                stream=stream,
                allow_failure=False,
            )
            if self._workspace_has_content(identifier, mode, clone_path, stream=stream):
                raise RuntimeError(
                    f"Workspace paths {target_root} and {clone_path} already contain files; cannot clone repository safely"
                )
            stream(
                {
                    "type": "status",
                    "stage": "clone",
                    "message": f"Workspace not empty; cloning repository into {clone_path}",
                }
            )

        command = self._wrap_exec(identifier, mode, ["git", "clone", repo_url, clone_path])

        def _masked_stream(event: dict[str, Any]) -> None:
            if access_token and isinstance(event, dict):
                masked_event = dict(event)
                if isinstance(masked_event.get("command"), str):
                    masked_event["command"] = masked_event["command"].replace(access_token, "****")
                    if safe_token:
                        masked_event["command"] = masked_event["command"].replace(safe_token, "****")
                if isinstance(masked_event.get("message"), str):
                    masked_event["message"] = masked_event["message"].replace(access_token, "****")
                    if safe_token:
                        masked_event["message"] = masked_event["message"].replace(safe_token, "****")
                stream(masked_event)
            else:
                stream(event)

        try:
            self.runner.run(command, stream=_masked_stream, allow_failure=False)
        except subprocess.CalledProcessError as exc:
            if access_token and isinstance(exc.output, str):
                sanitized = exc.output.replace(access_token, "****")
                if safe_token:
                    sanitized = sanitized.replace(safe_token, "****")
                exc.output = sanitized
            raise
        stream(
            {
                "type": "status",
                "stage": "clone",
                "message": f"Repository clone initiated from {redacted_repo_url} into {clone_path}",
            }
        )
        return clone_path

    def _create_feature_branch(
        self,
        *,
        identifier: str,
        mode: str,
        workspace_path: str,
        branch: str,
        stream: Callable[[dict[str, Any]], None],
    ) -> None:
        history_path = f"{workspace_path}/{self.config_dir}/history.jsonl"
        backup_path = f"{history_path}.bak"

        self.runner.run(
            self._wrap_exec(
                identifier,
                mode,
                ["sh", "-c", f"if [ -f {history_path} ]; then cp {history_path} {backup_path}; fi"],
            ),
            stream=stream,
            allow_failure=True,
        )

        checkout_command = self._wrap_exec(
            identifier,
            mode,
            ["git", "-C", workspace_path, "checkout", "-B", branch],
        )
        self.runner.run(checkout_command, stream=stream, allow_failure=False)

        fetch_command = self._wrap_exec(
            identifier,
            mode,
            ["git", "-C", workspace_path, "fetch", "origin", branch],
        )
        fetch_result = self.runner.run(fetch_command, stream=stream, allow_failure=True)
        if fetch_result.exit_code == 0:
            remote_ref_check = self._wrap_exec(
                identifier,
                mode,
                ["git", "-C", workspace_path, "rev-parse", "--verify", f"origin/{branch}"],
            )
            remote_ref = self.runner.run(remote_ref_check, stream=stream, allow_failure=True)
            if remote_ref.exit_code == 0:
                fast_forward_command = self._wrap_exec(
                    identifier,
                    mode,
                    ["git", "-C", workspace_path, "merge", "--ff-only", f"origin/{branch}"],
                )
                merge_result = self.runner.run(fast_forward_command, stream=stream, allow_failure=True)
                if merge_result.exit_code == 0:
                    stream(
                        {
                            "type": "status",
                            "stage": "git",
                            "message": f"Fast-forwarded branch {branch} to remote tip",
                        }
                    )

        self.runner.run(
            self._wrap_exec(
                identifier,
                mode,
                [
                    "sh",
                    "-c",
                    f"if [ -f {backup_path} ]; then cp {backup_path} {history_path}; rm {backup_path}; fi",
                ],
            ),
            stream=stream,
            allow_failure=True,
        )

        stream(
            {
                "type": "status",
                "stage": "workspace",
                "message": f"Checked out feature branch {branch}",
            }
        )

    def _final_message_path(self, workspace_path: str) -> str:
        return f"{workspace_path}/{self.config_dir}/final_message.txt"

    def _wrap_exec(self, identifier: str, mode: str, command: List[str]) -> List[str]:
        if mode == "docker":
            return ["docker", "exec", identifier, *command]
        if mode == "k8s":
            namespace, pod = self._split_k8s_identifier(identifier)
            exec_command: List[str] = ["kubectl", "exec"]
            if namespace:
                exec_command.extend(["-n", namespace])
            exec_command.extend([pod, "--", *command])
            return exec_command
        return command

    def _split_k8s_identifier(self, identifier: str) -> Tuple[str | None, str]:
        if "/" in identifier:
            namespace, pod = identifier.split("/", 1)
            return (namespace or None, pod)
        return None, identifier

    def _workspace_path(self, identifier: str, mode: str) -> str:
        if mode == "docker":
            return "/workspace"
        safe_identifier = identifier.split("/", 1)[-1].replace(":", "-")
        return f"/workspaces/{safe_identifier}"

    def _ensure_workspace_directory(
        self,
        identifier: str,
        mode: str,
        workspace_path: str,
        stream: Callable[[dict[str, Any]], None],
    ) -> None:
        command = self._wrap_exec(identifier, mode, ["mkdir", "-p", workspace_path])
        self.runner.run(command, stream=stream, allow_failure=False)

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
        request: Request,
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
        feature_branch = workspace.metadata.get("feature_branch")
        commit_hash = self._commit_and_push(
            request=request,
            workspace=workspace,
            branch=str(feature_branch) if isinstance(feature_branch, str) else None,
            stream=stream,
        )
        history_content = self._read_history_file(workspace, stream)
        final_message = self._read_final_message(workspace, stream)
        if not final_message and history_content:
            final_message = self._history_last_assistant(history_content)

        artifacts: Dict[str, str] = {}
        if isinstance(feature_branch, str) and feature_branch:
            artifacts["branch"] = feature_branch
        if history_content:
            artifacts["history"] = history_content
        if final_message:
            stream(
                {
                    "type": "assistant_message",
                    "stage": "chat",
                    "message": final_message,
                }
            )
            artifacts["final_message"] = final_message
        if commit_hash:
            artifacts["commit"] = commit_hash
        return ExecutionOutcome(diff=diff_output, artifacts=artifacts)

    def _sample_cpu_usage_seconds(self, workspace: WorkspaceContext) -> float | None:
        if getattr(self.runner, "dry_run", False):
            return None
        identifier = str(workspace.metadata.get("container") or workspace.ref or "").strip()
        if not identifier:
            return None
        mode = workspace.mode or ""
        if "://" in identifier:
            parsed_mode, parsed_identifier = self._parse_ref(identifier)
            mode = parsed_mode
            identifier = parsed_identifier
        if not identifier:
            return None
        script = build_cpu_probe_script()
        if mode == "docker":
            command = ["docker", "exec", identifier, "sh", "-c", script]
        elif mode in {"k8s", "kubernetes"}:
            namespace, pod = self._split_k8s_identifier(identifier)
            command = ["kubectl", "exec"]
            if namespace:
                command.extend(["-n", namespace])
            command.extend([pod, "--", "sh", "-c", script])
        else:
            return None
        result = self.runner.run(command, allow_failure=True)
        if result.exit_code != 0:
            logger.warning(
                "CPU probe command failed for workspace %s (%s): exit_code=%s",
                workspace.ref,
                mode,
                result.exit_code,
            )
            return None
        stdout = result.stdout or ""
        if not stdout.strip():
            logger.warning(
                "CPU probe returned no output for workspace %s (%s)",
                workspace.ref,
                mode,
            )
            return None
        seconds = parse_cpu_usage_payload(stdout)
        if seconds is None:
            return None
        return seconds

    def _workspace_for_request(self, request: Request) -> "Workspace | None":
        tenant_id = getattr(request, "tenant_id", "")
        workspace_meta = request.metadata.get("workspace") if isinstance(request.metadata, dict) else {}
        if not tenant_id and isinstance(workspace_meta, dict):
            tenant_id = workspace_meta.get("uid", "")
        tenant_id = str(tenant_id).strip() if tenant_id else ""
        if not tenant_id:
            return None
        try:
            from astraforge.accounts.models import Workspace
        except ModuleNotFoundError:
            return None
        try:
            return Workspace.objects.get(uid=tenant_id)
        except Workspace.DoesNotExist:
            return None

    def _quota_service(self) -> "WorkspaceQuotaService | None":
        try:
            from astraforge.quotas.services import get_quota_service
        except ModuleNotFoundError:
            return None
        return get_quota_service()

    def _commit_and_push(
        self,
        *,
        request: Request,
        workspace: WorkspaceContext,
        branch: str | None,
        stream: Callable[[dict[str, Any]], None],
    ) -> str | None:
        if not branch:
            return None
        identifier = workspace.metadata.get("container", workspace.ref)
        mode = workspace.mode
        path = workspace.path

        self._configure_git_identity(
            identifier=identifier,
            mode=mode,
            workspace_path=path,
            stream=stream,
        )

        self.runner.run(
            self._wrap_exec(
                identifier,
                mode,
                ["git", "-C", path, "add", "--all"],
            ),
            stream=stream,
            allow_failure=True,
        )
        # Exclude config dir from commits
        self.runner.run(
            self._wrap_exec(
                identifier,
                mode,
                [
                    "git",
                    "-C",
                    path,
                    "restore",
                    "--staged",
                    "--",
                    self.config_dir,
                ],
            ),
            stream=stream,
            allow_failure=True,
        )
        self.runner.run(
            self._wrap_exec(
                identifier,
                mode,
                ["git", "-C", path, "reset", "HEAD", "--", self.config_dir],
            ),
            stream=stream,
            allow_failure=True,
        )
        self.runner.run(
            self._wrap_exec(
                identifier,
                mode,
                [
                    "git",
                    "-C",
                    path,
                    "rm",
                    "--cached",
                    "--ignore-unmatch",
                    "-r",
                    self.config_dir,
                ],
            ),
            stream=stream,
            allow_failure=True,
        )

        status_command = self._wrap_exec(
            identifier,
            mode,
            ["git", "-C", path, "status", "--porcelain"],
        )
        status_result = self.runner.run(status_command, stream=stream, allow_failure=True)
        if not (status_result.stdout or "").strip():
            stream(
                {
                    "type": "status",
                    "stage": "git",
                    "message": "Working tree clean; skipping commit and push",
                }
            )
            return None

        commit_message = f"AstraForge request {request.id}"
        commit_command = self._wrap_exec(
            identifier,
            mode,
            ["git", "-C", path, "commit", "-m", commit_message],
        )
        commit_result = self.runner.run(commit_command, stream=stream, allow_failure=True)
        if commit_result.exit_code != 0:
            stream(
                {
                    "type": "status",
                    "stage": "git",
                    "message": "Git commit reported no changes; skipping push",
                }
            )
            return None

        push_command = self._wrap_exec(
            identifier,
            mode,
            ["git", "-C", path, "push", "-u", "origin", branch],
        )
        try:
            self.runner.run(push_command, stream=stream, allow_failure=False)
        except subprocess.CalledProcessError as exc:
            output_text = (exc.output or "").lower()
            non_fast_forward = "non-fast-forward" in output_text or "fetch first" in output_text
            if not non_fast_forward:
                raise
            stream(
                {
                    "type": "status",
                    "stage": "git",
                    "message": f"Remote branch {branch} is ahead; rebasing before retry",
                }
            )
            fetch_retry = self.runner.run(
                self._wrap_exec(
                    identifier,
                    mode,
                    ["git", "-C", path, "fetch", "origin", branch],
                ),
                stream=stream,
                allow_failure=True,
            )
            if fetch_retry.exit_code != 0:
                raise
            rebase_command = self._wrap_exec(
                identifier,
                mode,
                ["git", "-C", path, "pull", "--rebase", "origin", branch],
            )
            rebase_result = self.runner.run(rebase_command, stream=stream, allow_failure=True)
            if rebase_result.exit_code != 0:
                raise
            retry_push = self.runner.run(push_command, stream=stream, allow_failure=True)
            if retry_push.exit_code != 0:
                raise
        
        stream(
            {
                "type": "status",
                "stage": "git",
                "message": f"Pushed branch {branch} to origin",
            }
        )
        rev_parse = self.runner.run(
            self._wrap_exec(identifier, mode, ["git", "-C", path, "rev-parse", "HEAD"]),
            stream=stream,
            allow_failure=True,
        )
        return (rev_parse.stdout or "").strip() if rev_parse.exit_code == 0 else None

    def _configure_git_identity(
        self,
        *,
        identifier: str,
        mode: str,
        workspace_path: str,
        stream: Callable[[dict[str, Any]], None],
    ) -> None:
        name = os.getenv("ASTRAFORGE_GIT_AUTHOR_NAME", "AstraForge Bot")
        email = os.getenv("ASTRAFORGE_GIT_AUTHOR_EMAIL", "bot@astraforge.local")
        commands = [
            ["git", "-C", workspace_path, "config", "user.name", name],
            ["git", "-C", workspace_path, "config", "user.email", email],
        ]
        for args in commands:
            command = self._wrap_exec(identifier, mode, args)
            self.runner.run(command, stream=stream, allow_failure=True)

    def _restore_history_from_metadata(
        self,
        *,
        identifier: str,
        mode: str,
        workspace_path: str,
        history_content: str | None,
        stream: Callable[[dict[str, Any]], None],
    ) -> None:
        if not history_content:
            return
        encoded = base64.b64encode(history_content.encode("utf-8")).decode("ascii")
        repo_history = f"{workspace_path}/{self.config_dir}/history.jsonl"
        home_history = f"$HOME/{self.config_dir}/history.jsonl"
        script = (
            f"mkdir -p {workspace_path}/{self.config_dir} $HOME/{self.config_dir} && "
            f"echo '{encoded}' | base64 -d | tee {repo_history} {home_history} >/dev/null"
        )
        command = self._wrap_exec(identifier, mode, ["sh", "-c", script])
        self.runner.run(command, stream=stream, allow_failure=True)
        stream(
            {
                "type": "status",
                "stage": "workspace",
                "message": f"Restored {self.agent_name} history from previous run",
            }
        )

    def _read_history_file(
        self,
        workspace: WorkspaceContext,
        stream: Callable[[dict[str, Any]], None],
    ) -> str | None:
        identifier = workspace.metadata.get("container", workspace.ref)
        mode = workspace.mode
        repo_history = f"{workspace.path}/{self.config_dir}/history.jsonl"
        home_history = f"$HOME/{self.config_dir}/history.jsonl"
        for candidate in (home_history, repo_history):
            command = self._wrap_exec(
                identifier,
                mode,
                ["sh", "-c", f"if [ -f {candidate} ]; then cat {candidate}; fi"],
            )
            result = self.runner.run(command, stream=stream, allow_failure=True)
            content = (result.stdout or "").strip()
            if content:
                return content
        return None

    def _read_final_message(
        self,
        workspace: WorkspaceContext,
        stream: Callable[[dict[str, Any]], None],
    ) -> str | None:
        identifier = workspace.metadata.get("container", workspace.ref)
        mode = workspace.mode
        final_path = self._final_message_path(workspace.path)
        command = self._wrap_exec(
            identifier,
            mode,
            ["sh", "-c", f"if [ -f {final_path} ]; then cat {final_path}; fi"],
        )
        result = self.runner.run(command, stream=stream, allow_failure=True)
        message = (result.stdout or "").strip()
        if message:
            stream(
                {
                    "type": "status",
                    "stage": self.agent_name,
                    "message": f"Captured final {self.agent_name} response",
                }
            )
            return message
        return None

    def _history_last_assistant(self, history_content: str | None) -> str | None:
        if not history_content:
            return None
        lines = [line.strip() for line in history_content.splitlines() if line.strip()]
        for raw in reversed(lines):
            role = "assistant"
            content: str | None = None
            try:
                record = json.loads(raw)
            except json.JSONDecodeError:
                content = raw
            else:
                role = str(
                    record.get("role")
                    or record.get("author")
                    or record.get("type")
                    or "assistant"
                ).lower()
                content = self._normalize_history_content(record.get("content"))
                if not content:
                    content = self._normalize_history_content(record.get("message"))
            if not content:
                continue
            if role in {"assistant", "ai", "model", self.agent_name}:
                normalized = content.strip()
                if normalized:
                    return normalized
        return None

    @staticmethod
    def _normalize_history_content(value: object) -> str | None:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            if parts:
                return "\n".join(parts)
        return None

    def _ensure_local_image(
        self,
        image: str,
        stream: Callable[[dict[str, Any]], None],
    ) -> None:
        # Default implementation might not be enough if agents have different build contexts
        pass
