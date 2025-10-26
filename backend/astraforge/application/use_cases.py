"""Application-layer use cases orchestrating AstraForge request lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
import subprocess
from typing import TYPE_CHECKING, Any, Protocol

from astraforge.domain.models.request import ExecutionPlan, Request, RequestState
from astraforge.domain.models.spec import DevelopmentSpec
from astraforge.domain.models.workspace import ExecutionOutcome, WorkspaceContext

if TYPE_CHECKING:
    from astraforge.domain.providers.interfaces import (
        AgentExecutor,
        MergeRequestComposer,
        Provisioner,
        RunLogStreamer,
        SpecGenerator,
        VCSProvider,
        WorkspaceOperator,
    )


class RequestRepository(Protocol):
    """Persistence boundary for request aggregates."""

    def save(self, request: Request) -> None:  # pragma: no cover
        ...

    def get(self, request_id: str) -> Request:  # pragma: no cover
        ...


@dataclass
class SubmitRequest:
    repository: RequestRepository

    def __call__(self, request: Request) -> Request:
        request.transition(RequestState.RECEIVED)
        self.repository.save(request)
        return request


@dataclass
class ProcessRequest:
    repository: RequestRepository
    spec_generator: "SpecGenerator"
    run_log: "RunLogStreamer"

    def __call__(self, request_id: str) -> DevelopmentSpec:
        request = self.repository.get(request_id)
        self._emit(
            request,
            {"type": "status", "stage": "spec", "message": "Generating development spec"},
        )
        try:
            spec = self.spec_generator.generate(request)
        except Exception as exc:
            request.transition(RequestState.FAILED)
            self.repository.save(request)
            self._emit(
                request,
                {
                    "type": "error",
                    "stage": "failed",
                    "message": str(exc),
                },
            )
            raise

        spec_dict = spec.as_dict()
        request.metadata["spec"] = spec_dict
        request.transition(RequestState.SPEC_READY)
        self.repository.save(request)
        self._emit(
            request,
            {
                "type": "spec_ready",
                "message": "Specification generated",
                "spec": spec_dict,
            },
        )
        return spec

    def _emit(self, request: Request, event: dict[str, object]) -> None:
        payload = {"request_id": request.id, **event}
        self.run_log.publish(request.id, payload)


@dataclass
class ExecuteRequest:
    repository: RequestRepository
    workspace_operator: "WorkspaceOperator"
    run_log: "RunLogStreamer"

    def __call__(
        self,
        request_id: str,
        *,
        spec_override: dict[str, Any] | None = None,
    ) -> ExecutionOutcome:
        request = self.repository.get(request_id)
        current_spec = spec_override or request.metadata.get("spec")
        if current_spec is None:
            spec = self._default_spec_from_request(request)
        else:
            spec = self._hydrate_spec(current_spec)
        request.metadata["spec"] = spec.as_dict()
        self.repository.save(request)

        self._emit(
            request,
            {
                "type": "status",
                "stage": "provisioning",
                "message": "Provisioning workspace",
            },
        )
        request.transition(RequestState.EXECUTING)
        self.repository.save(request)

        workspace: WorkspaceContext | None = None
        try:
            workspace = self.workspace_operator.prepare(
                request,
                spec,
                stream=lambda event: self._emit(request, event),
            )
            request.metadata["workspace"] = workspace.as_dict()
            self.repository.save(request)

            outcome = self.workspace_operator.run_codex(
                request,
                spec,
                workspace,
                stream=lambda event: self._emit(request, event),
            )
            request.metadata["execution"] = outcome.as_dict()
            request.transition(RequestState.PATCH_READY)
            self.repository.save(request)
            self._emit(
                request,
                {"type": "completed", "message": "Execution finished"},
            )
            return outcome
        except subprocess.CalledProcessError as exc:
            request.metadata.setdefault("execution_errors", []).append(
                {
                    "command": " ".join(str(part) for part in exc.cmd),
                    "exit_code": exc.returncode,
                    "output": (exc.output or "").strip(),
                }
            )
            request.transition(RequestState.FAILED)
            self.repository.save(request)
            message = exc.output.strip() if isinstance(exc.output, str) else str(exc)
            self._emit(
                request,
                {
                    "type": "error",
                    "stage": "failed",
                    "message": message or "Command execution failed",
                },
            )
            raise RuntimeError(message or "Command execution failed") from exc
        except Exception as exc:
            request.transition(RequestState.FAILED)
            self.repository.save(request)
            self._emit(
                request,
                {
                    "type": "error",
                    "stage": "failed",
                    "message": str(exc),
                },
            )
            raise
        finally:
            if workspace is not None:
                self.workspace_operator.teardown(workspace)

    def _emit(self, request: Request, event: dict[str, object]) -> None:
        payload = {"request_id": request.id, **event}
        self.run_log.publish(request.id, payload)

    def _hydrate_spec(self, data: dict[str, Any]) -> DevelopmentSpec:
        return DevelopmentSpec(
            title=str(data.get("title", "")),
            summary=str(data.get("summary", "")),
            requirements=list(data.get("requirements", []) or []),
            implementation_steps=list(data.get("implementation_steps", []) or []),
            risks=list(data.get("risks", []) or []),
            acceptance_criteria=list(data.get("acceptance_criteria", []) or []),
        )

    def _default_spec_from_request(self, request: Request) -> DevelopmentSpec:
        prompt = request.payload.description or ""
        title = request.payload.title or self._fallback_title(prompt)
        summary = prompt or title
        implementation_steps: list[str] = []
        if prompt:
            implementation_steps.append(prompt)
        return DevelopmentSpec(
            title=title or "User request",
            summary=summary or "User request",
            implementation_steps=implementation_steps,
        )

    @staticmethod
    def _fallback_title(prompt: str) -> str:
        clean = prompt.strip()
        if not clean:
            return "User request"
        first_line = clean.split("\n", 1)[0].strip()
        candidate = first_line if first_line else clean
        limit = 72
        return candidate if len(candidate) <= limit else f"{candidate[: limit - 3]}..."


@dataclass
class SubmitMergeRequest:
    repository: RequestRepository
    composer: "MergeRequestComposer"
    vcs: "VCSProvider"
    run_log: "RunLogStreamer | None" = None

    def __call__(self, request_id: str) -> str:
        request = self.repository.get(request_id)
        raw_outcome = request.metadata.get("execution")
        if not raw_outcome:
            raise ValueError("Execution outcome missing; run Codex before opening MR")
        outcome = ExecutionOutcome(
            diff=raw_outcome.get("diff", ""),
            reports=raw_outcome.get("reports", {}),
            artifacts=raw_outcome.get("artifacts", {}),
        )
        proposal = self.composer.compose(request, outcome)
        project = request.metadata.get("project", {})
        repository_slug = project.get("repository")
        if not repository_slug:
            raise ValueError("Request metadata is missing repository information")
        mr_ref = self.vcs.open_mr(
            repo=repository_slug,
            branch=proposal.target_branch,
            title=proposal.title,
            body=proposal.description,
            artifacts=[outcome.diff],
        )
        request.metadata.setdefault("mr", {})
        request.metadata["mr"].update({**proposal.as_dict(), "ref": mr_ref})
        request.transition(RequestState.MR_OPENED)
        self.repository.save(request)
        if self.run_log is not None:
            self.run_log.publish(
                request.id,
                {
                    "request_id": request.id,
                    "type": "status",
                    "stage": "mr",
                    "message": f"Merge request opened: {mr_ref}",
                },
            )
        return mr_ref


@dataclass
class BootstrapEnvironment:
    repository: RequestRepository
    provisioner: "Provisioner"
    executor: "AgentExecutor"

    def __call__(self, request: Request) -> dict[str, str]:
        project = request.metadata.get("project") or {}
        repository_slug = project.get("repository")
        if not repository_slug:
            raise ValueError("Request is missing project repository metadata")

        branch = project.get("branch") or "main"
        toolchain = getattr(self.executor, "name", "codex")
        sanitized_repo = repository_slug.replace("/", "-")
        workspace_ref = self.provisioner.spawn(
            repo=sanitized_repo, toolchain=toolchain
        )

        mode = getattr(self.provisioner, "name", "workspace")
        image = getattr(self.provisioner, "image", None)
        environment = {
            "status": "ready",
            "workspace_ref": workspace_ref,
            "repository": repository_slug,
            "branch": branch,
            "mode": mode,
            "image": image or "",
        }
        executor_info = {
            "name": getattr(self.executor, "name", "executor"),
            "status": "launched",
            "launch_command": self._launch_command(
                mode=mode,
                workspace_ref=workspace_ref,
                repository=repository_slug,
                branch=branch,
            ),
        }

        request.metadata["environment"] = environment
        request.metadata["executor"] = executor_info
        request.transition(RequestState.SPEC_READY)
        self.repository.save(request)
        return environment

    def _launch_command(
        self,
        *,
        mode: str,
        workspace_ref: str,
        repository: str,
        branch: str,
    ) -> str:
        if mode == "docker":
            return (
                f"docker run --rm -e REPOSITORY={repository} -e BRANCH={branch} "
                f"{getattr(self.provisioner, 'image', 'astraforge/codex-cli:latest')}"
            )
        if mode == "k8s":
            return (
                f"kubectl exec {workspace_ref} -- codex-cli --repo {repository} "
                f"--branch {branch}"
            )
        return f"codex-cli --repo {repository} --branch {branch}"


@dataclass
class GeneratePlan:
    repository: RequestRepository
    executor: AgentExecutor

    def __call__(self, request_id: str) -> ExecutionPlan:
        request = self.repository.get(request_id)
        plan = self.executor.plan(request)
        request.metadata["plan"] = plan
        request.transition(RequestState.PLAN_READY)
        self.repository.save(request)
        return plan


@dataclass
class ApplyPlan:
    repository: RequestRepository
    executor: AgentExecutor
    vcs: VCSProvider
    provisioner: Provisioner

    def __call__(self, request_id: str, repo: str, branch: str) -> str:
        request = self.repository.get(request_id)
        plan: ExecutionPlan = request.metadata["plan"]
        workspace_ref = self.provisioner.spawn(repo, toolchain="default")
        try:
            change_set = self.executor.apply(plan, repo, workspace_ref)
            request.metadata["change_set"] = change_set
            request.transition(RequestState.PATCH_READY)
            self.repository.save(request)
            mr_ref = self.vcs.open_mr(
                repo=repo,
                branch=branch,
                title=request.payload.title,
                body=request.payload.description,
                artifacts=[change_set.diff_uri],
            )
            request.metadata["mr_ref"] = mr_ref
            request.transition(RequestState.MR_OPENED)
            self.repository.save(request)
            return mr_ref
        finally:
            self.provisioner.cleanup(workspace_ref)
