"""Connector implementations that translate external payloads into domain requests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from astraforge.domain.models.request import Attachment, Request, RequestPayload
from astraforge.domain.providers.interfaces import Connector


@dataclass
class DirectUserConnector(Connector):
    tenant_id: str

    def parse_inbound(self, payload: dict) -> Request:
        request_payload = RequestPayload(
            title=payload["title"],
            description=payload["description"],
            context=payload.get("context", {}),
            attachments=[Attachment(**att) for att in payload.get("attachments", [])],
        )
        return Request(
            id=str(uuid.uuid4()),
            tenant_id=self.tenant_id,
            source="direct_user",
            sender=payload.get("sender", ""),
            payload=request_payload,
        )

    def ack(self, external_id: str) -> None:  # nothing to ack for web submissions
        return None


def from_env(tenant_id: str | None = None) -> DirectUserConnector:
    import os

    resolved: str = tenant_id or os.getenv("DEFAULT_TENANT_ID", "default")
    return DirectUserConnector(tenant_id=resolved)
