"""Versioned events emitted by the AstraForge orchestration pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping


@dataclass(slots=True, frozen=True)
class Event:
    name: str
    version: int
    payload: Mapping[str, Any]
    timestamp: datetime


REQUEST_EVENTS_V1 = {
    "request.received": "request.received.v1",
    "spec.ready": "spec.ready.v1",
    "plan.ready": "plan.ready.v1",
    "env.ready": "env.ready.v1",
    "patch.ready": "patch.ready.v1",
    "mr.opened": "mr.opened.v1",
    "review.ready": "review.ready.v1",
    "run.failed": "run.failed.v1",
}
