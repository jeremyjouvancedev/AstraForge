"""Celery tasks orchestrating request lifecycle events."""

from __future__ import annotations

from celery import shared_task

from astraforge.application.use_cases import (
    ApplyPlan,
    GeneratePlan,
    ExecuteRequest,
    ProcessRequest,
    SubmitMergeRequest,
)
from astraforge.bootstrap import container, repository


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True)
def generate_plan_task(self, request_id: str) -> dict:
    plan = GeneratePlan(repository=repository, executor=container.resolve_executor())(
        request_id
    )
    return {"steps": [step.description for step in plan.steps], "summary": plan.summary}


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True)
def apply_plan_task(self, request_id: str, repo: str, branch: str) -> str:
    return ApplyPlan(
        repository=repository,
        executor=container.resolve_executor(),
        vcs=container.vcs_providers.resolve("gitlab"),
        provisioner=container.resolve_provisioner(),
    )(request_id=request_id, repo=repo, branch=branch)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True)
def generate_spec_task(self, request_id: str) -> dict:
    spec = ProcessRequest(
        repository=repository,
        spec_generator=container.resolve_spec_generator(),
        run_log=container.resolve_run_log(),
    )(request_id)
    return spec.as_dict()


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True)
def execute_request_task(self, request_id: str, spec: dict | None = None) -> dict:
    outcome = ExecuteRequest(
        repository=repository,
        workspace_operator=container.resolve_workspace_operator(),
        run_log=container.resolve_run_log(),
    )(request_id=request_id, spec_override=spec)
    return outcome.as_dict()


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True)
def submit_merge_request_task(self, request_id: str) -> str:
    return SubmitMergeRequest(
        repository=repository,
        composer=container.resolve_merge_request_composer(),
        vcs=container.vcs_providers.resolve("gitlab"),
        run_log=container.resolve_run_log(),
    )(request_id)
