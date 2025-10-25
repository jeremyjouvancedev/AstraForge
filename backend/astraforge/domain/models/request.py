"""Domain objects for handling inbound work requests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class RequestState(str, Enum):
    RECEIVED = "RECEIVED"
    SPEC_READY = "SPEC_READY"
    CHAT_REVIEWED = "CHAT_REVIEWED"
    PLAN_READY = "PLAN_READY"
    EXECUTING = "EXECUTING"
    PATCH_READY = "PATCH_READY"
    MR_OPENED = "MR_OPENED"
    REVIEWED = "REVIEWED"
    DONE = "DONE"
    FAILED = "FAILED"


@dataclass(slots=True)
class Attachment:
    uri: str
    name: str
    content_type: str


@dataclass(slots=True)
class RequestPayload:
    title: str
    description: str
    context: Dict[str, Any]
    attachments: List[Attachment] = field(default_factory=list)


@dataclass(slots=True)
class Request:
    id: str
    tenant_id: str
    source: str
    sender: str
    payload: RequestPayload
    state: RequestState = RequestState.RECEIVED
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def transition(self, target: RequestState) -> None:
        """Advance the request to a new state, enforcing allowed transitions."""
        if target == self.state:
            return
        if target not in _ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(f"Invalid transition {self.state} -> {target}")
        self.state = target
        self.updated_at = datetime.utcnow()


_ALLOWED_TRANSITIONS: Dict[RequestState, List[RequestState]] = {
    RequestState.RECEIVED: [RequestState.SPEC_READY, RequestState.FAILED],
    RequestState.SPEC_READY: [
        RequestState.CHAT_REVIEWED,
        RequestState.EXECUTING,
        RequestState.FAILED,
    ],
    RequestState.CHAT_REVIEWED: [RequestState.PLAN_READY, RequestState.FAILED],
    RequestState.PLAN_READY: [RequestState.EXECUTING, RequestState.FAILED],
    RequestState.EXECUTING: [RequestState.PATCH_READY, RequestState.FAILED],
    RequestState.PATCH_READY: [RequestState.EXECUTING, RequestState.MR_OPENED, RequestState.FAILED],
    RequestState.MR_OPENED: [RequestState.REVIEWED, RequestState.FAILED],
    RequestState.REVIEWED: [RequestState.DONE, RequestState.FAILED],
    RequestState.DONE: [],
    RequestState.FAILED: [RequestState.SPEC_READY, RequestState.EXECUTING],
}


@dataclass(slots=True)
class ChangeSet:
    diff_uri: str
    reports: Dict[str, Any]


@dataclass(slots=True)
class PlanStep:
    description: str
    completed: bool = False
    risk: Optional[str] = None


@dataclass(slots=True)
class ExecutionPlan:
    steps: List[PlanStep]
    summary: str
