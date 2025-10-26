"""Microsoft Teams connector implementation."""

from __future__ import annotations

from dataclasses import dataclass

from astraforge.domain.models.request import Request
from astraforge.infrastructure.connectors.base import DirectUserConnector


@dataclass
class TeamsConnector(DirectUserConnector):
    def parse_inbound(self, payload: dict) -> Request:
        card = payload.get("card", {})
        normalized = {
            "title": card.get("title", ""),
            "description": card.get("text", ""),
            "context": {"conversation_id": payload.get("conversation_id")},
            "attachments": payload.get("attachments", []),
            "sender": payload.get("from", {}).get("user", {}).get("id", ""),
        }
        return super().parse_inbound(normalized)


def from_env(tenant_id: str | None = None):
    import os

    resolved: str = tenant_id or os.getenv("DEFAULT_TENANT_ID", "default")
    return TeamsConnector(tenant_id=resolved)
