"""Jira connector implementation."""

from __future__ import annotations

from dataclasses import dataclass

from astraforge.domain.models.request import Request
from astraforge.infrastructure.connectors.base import DirectUserConnector


@dataclass
class JiraConnector(DirectUserConnector):
    def parse_inbound(self, payload: dict) -> Request:
        normalized = {
            "title": payload["summary"],
            "description": payload.get("description", ""),
            "context": {
                "issue_key": payload["issue_key"],
                "labels": payload.get("labels", []),
            },
            "attachments": payload.get("attachments", []),
            "sender": payload.get("reporter", ""),
        }
        return super().parse_inbound(normalized)


def from_env(tenant_id: str | None = None):
    import os

    resolved: str = tenant_id or os.getenv("DEFAULT_TENANT_ID", "default")
    return JiraConnector(tenant_id=resolved)
