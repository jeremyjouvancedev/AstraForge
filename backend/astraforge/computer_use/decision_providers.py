from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Protocol

from .protocol import (
    ComputerCall,
    ComputerCallAction,
    ComputerCallMeta,
    DecisionRequest,
    DecisionResponse,
    PendingSafetyCheck,
    ensure_call_id,
    ensure_response_id,
)


class DecisionProvider(Protocol):
    def decide(self, request: DecisionRequest) -> DecisionResponse:  # pragma: no cover - protocol
        ...


@dataclass(slots=True)
class ScriptedDecisionProvider:
    script: list[dict[str, Any]]

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        index = request.step_index
        if index < len(self.script):
            entry = self.script[index]
        else:
            entry = {"action": {"type": "terminate"}}

        call = _call_from_entry(entry)
        call.action.validate()
        call = ensure_call_id(call)
        response_id = ensure_response_id(entry.get("response_id"))
        reasoning_summary = None
        meta = entry.get("meta")
        if isinstance(meta, dict):
            reasoning_summary = meta.get("reasoning_summary")
        return DecisionResponse(
            response_id=response_id,
            computer_call=call,
            reasoning_summary=reasoning_summary,
        )


def _call_from_entry(entry: dict[str, Any]) -> ComputerCall:
    if "computer_call" in entry:
        raw_call = entry["computer_call"] or {}
        return ComputerCall.from_dict(raw_call)

    action = ComputerCallAction.from_dict(entry.get("action") or {})
    meta = ComputerCallMeta.from_dict(entry.get("meta"))
    pending = [
        PendingSafetyCheck.from_dict(item)
        for item in (entry.get("pending_safety_checks") or [])
    ]
    return ComputerCall(
        call_id=str(entry.get("call_id") or ""),
        action=action,
        meta=meta,
        pending_safety_checks=pending,
    )


def build_policy_summary(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "allowed_domains": list(config.get("allowed_domains") or []),
        "blocked_domains": list(config.get("blocked_domains") or []),
        "approval_mode": config.get("approval_mode", "auto"),
        "allow_login": bool(config.get("allow_login", False)),
        "allow_payments": bool(config.get("allow_payments", False)),
        "allow_irreversible": bool(config.get("allow_irreversible", False)),
        "allow_credentials": bool(config.get("allow_credentials", False)),
    }


def normalize_script(raw: Iterable[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    return [dict(item) for item in raw]
