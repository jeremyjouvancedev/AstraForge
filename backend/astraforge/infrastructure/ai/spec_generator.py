"""HTTP proxy-backed development specification generator."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict

import requests
from requests import Response

from astraforge.domain.models.request import Request
from astraforge.domain.models.spec import DevelopmentSpec
from astraforge.domain.providers.interfaces import SpecGenerator

DEFAULT_TIMEOUT = int(os.getenv("LLM_PROXY_TIMEOUT", "60"))


@dataclass
class ProxySpecGenerator(SpecGenerator):
    """Delegates specification generation to an external proxy service."""

    endpoint: str
    timeout: int = field(default=DEFAULT_TIMEOUT)

    def generate(self, request: Request) -> DevelopmentSpec:
        payload = {
            "title": request.payload.title,
            "description": request.payload.description,
            "context": request.payload.context,
            "repository": request.metadata.get("project", {}).get("repository", "unknown"),
            "branch": request.metadata.get("project", {}).get("branch", "main"),
        }
        response = self._post("/spec", json=payload)
        data = response.json()
        return DevelopmentSpec(
            title=data.get("title", request.payload.title),
            summary=data.get("summary", request.payload.description[:200]),
            requirements=list(data.get("requirements", [])),
            implementation_steps=list(data.get("implementation_steps", [])),
            risks=list(data.get("risks", [])),
            acceptance_criteria=list(data.get("acceptance_criteria", [])),
        )

    def _post(self, path: str, *, json: Dict[str, Any]) -> Response:
        url = f"{self.endpoint}{path}"
        try:
            response = requests.post(url, json=json, timeout=self.timeout)
        except requests.RequestException as exc:  # pragma: no cover - network error path
            raise RuntimeError(f"Failed to reach LLM proxy at {self.endpoint}: {exc}") from exc
        if response.status_code >= 400:
            detail = self._safe_detail(response)
            raise RuntimeError(
                f"LLM proxy request failed with status {response.status_code}: {detail}"
            )
        return response

    def _safe_detail(self, response: Response) -> str:
        try:
            data = response.json()
            if isinstance(data, dict) and "detail" in data:
                return str(data["detail"])
            return str(data)
        except ValueError:  # pragma: no cover - non-JSON response
            return response.text[:200]


def from_env() -> ProxySpecGenerator:
    endpoint = os.getenv("LLM_PROXY_URL", "http://llm-proxy:8080")
    return ProxySpecGenerator(endpoint=endpoint)
