"""LLM proxy backed merge request composer."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict

import requests

from astraforge.domain.models.request import Request
from astraforge.domain.models.spec import MergeRequestProposal
from astraforge.domain.models.workspace import ExecutionOutcome
from astraforge.domain.providers.interfaces import MergeRequestComposer

DEFAULT_TIMEOUT = int(os.getenv("LLM_PROXY_TIMEOUT", "60"))


@dataclass
class ProxyMergeRequestComposer(MergeRequestComposer):
    endpoint: str
    timeout: int = field(default=DEFAULT_TIMEOUT)

    def compose(self, request: Request, outcome: ExecutionOutcome) -> MergeRequestProposal:
        project = request.metadata.get("project", {})
        payload: Dict[str, Any] = {
            "title": request.payload.title,
            "repository": project.get("repository", "unknown"),
            "target_branch": project.get("branch", "main"),
            "source_branch": outcome.artifacts.get("branch", f"astraforge/{request.id}"),
            "diff": outcome.diff[:8000],
            "reports": outcome.reports,
        }
        response = self._post("/merge-request", json=payload)
        data = response.json()
        return MergeRequestProposal(
            title=data.get("title", request.payload.title),
            description=data.get("description", ""),
            target_branch=data.get("target_branch", payload["target_branch"]),
            source_branch=data.get("source_branch", payload["source_branch"]),
        )

    def _post(self, path: str, *, json: Dict[str, Any]) -> requests.Response:
        url = f"{self.endpoint}{path}"
        try:
            response = requests.post(url, json=json, timeout=self.timeout)
        except requests.RequestException as exc:  # pragma: no cover - network error path
            raise RuntimeError(f"Failed to reach LLM proxy at {self.endpoint}: {exc}") from exc
        if response.status_code >= 400:
            detail = self._safe_detail(response)
            raise RuntimeError(
                f"LLM proxy merge request failed with status {response.status_code}: {detail}"
            )
        return response

    def _safe_detail(self, response: requests.Response) -> str:
        try:
            data = response.json()
            if isinstance(data, dict) and "detail" in data:
                return str(data["detail"])
            return str(data)
        except ValueError:  # pragma: no cover - non-JSON response
            return response.text[:200]


def from_env() -> ProxyMergeRequestComposer:
    endpoint = os.getenv("LLM_PROXY_URL", "http://llm-proxy:8080")
    return ProxyMergeRequestComposer(endpoint=endpoint)
