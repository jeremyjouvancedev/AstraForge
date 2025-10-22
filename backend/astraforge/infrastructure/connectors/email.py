"""Email connector implementation."""

from __future__ import annotations

from dataclasses import dataclass

from astraforge.domain.models.request import Request
from astraforge.infrastructure.connectors.base import DirectUserConnector


@dataclass
class EmailConnector(DirectUserConnector):
    def parse_inbound(self, payload: dict) -> Request:
        normalized = {
            "title": payload.get("subject", ""),
            "description": payload.get("body", ""),
            "context": {"message_id": payload.get("message_id")},
            "attachments": payload.get("attachments", []),
            "sender": payload.get("from", ""),
        }
        return super().parse_inbound(normalized)


def from_env(tenant_id: str | None = None):
    import os

    resolved: str = tenant_id or os.getenv("DEFAULT_TENANT_ID", "default")
    return EmailConnector(tenant_id=resolved)
