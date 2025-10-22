"""Celery tasks orchestrating request lifecycle events."""

from __future__ import annotations

from celery import shared_task

from astraforge.application.use_cases import ApplyPlan, GeneratePlan
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
        provisioner=container.provisioners.resolve("k8s"),
    )(request_id=request_id, repo=repo, branch=branch)
