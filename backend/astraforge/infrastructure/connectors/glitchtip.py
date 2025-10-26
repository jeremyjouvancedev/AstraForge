"""GlitchTip connector implementation."""

from __future__ import annotations

from dataclasses import dataclass

from astraforge.domain.models.request import Request
from astraforge.infrastructure.connectors.base import DirectUserConnector


@dataclass
class GlitchTipConnector(DirectUserConnector):
    def parse_inbound(self, payload: dict) -> Request:
        event = payload.get("event", {})
        normalized = {
            "title": event.get("title", "GlitchTip Alert"),
            "description": event.get("message", ""),
            "context": {
                "event_id": event.get("id"),
                "project": payload.get("project", {}),
            },
            "attachments": [],
            "sender": payload.get("actor", {}).get("email", ""),
        }
        return super().parse_inbound(normalized)


def from_env(tenant_id: str | None = None):
    import os

    resolved: str = tenant_id or os.getenv("DEFAULT_TENANT_ID", "default")
    return GlitchTipConnector(tenant_id=resolved)
