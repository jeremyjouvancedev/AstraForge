"""Versioned message contracts for AstraForge event bus."""

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(slots=True)
class RequestReceivedV1:
    request_id: str
    source: str
    payload: Dict[str, Any]


EVENT_CONTRACTS = {
    "request.received.v1": RequestReceivedV1,
}
