"""Application-layer use cases orchestrating AstraForge request lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from astraforge.domain.models.request import ExecutionPlan, Request, RequestState

if TYPE_CHECKING:
    from astraforge.domain.providers.interfaces import (
        AgentExecutor,
        Provisioner,
        VCSProvider,
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
