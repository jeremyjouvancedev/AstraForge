from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable


ACTION_TYPES = {
    "click",
    "double_click",
    "type",
    "scroll",
    "keypress",
    "visit_url",
    "tavily_search",
    "back",
    "wait",
    "terminate",
    "navigate",
    "go_back",
    "input",
    "upload_file",
    "find_text",
    "send_keys",
    "evaluate",
    "switch",
    "close",
    "extract",
    "screenshot",
    "dropdown_options",
    "select_dropdown",
    "write_file",
    "read_file",
    "replace_file",
}


def new_call_id() -> str:
    return str(uuid.uuid4())


def new_step_id() -> str:
    return str(uuid.uuid4())


def new_response_id() -> str:
    return str(uuid.uuid4())


def new_safety_check_id(prefix: str = "sc") -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


@dataclass(slots=True)
class PendingSafetyCheck:
    id: str
    category: str
    severity: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "severity": self.severity,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PendingSafetyCheck":
        return cls(
            id=str(raw.get("id") or ""),
            category=str(raw.get("category") or ""),
            severity=str(raw.get("severity") or ""),
            message=str(raw.get("message") or ""),
        )


@dataclass(slots=True)
class ComputerCallAction:
    type: str
    x: int | None = None
    y: int | None = None
    index: int | None = None
    button: str | None = None
    text: str | None = None
    url: str | None = None
    query: str | None = None
    scroll_dx: int | None = None
    scroll_dy: int | None = None
    keys: list[str] | None = None
    seconds: float | None = None
    path: str | None = None
    script: str | None = None

    def validate(self) -> None:
        if self.type not in ACTION_TYPES:
            raise ValueError(f"Unsupported action type '{self.type}'")
        if self.type in {"click", "double_click", "type", "input"}:
            if self.index is None and (self.x is None or self.y is None):
                raise ValueError(f"{self.type} requires index or (x and y)")
        if self.type in {"type", "input"} and not self.text:
            raise ValueError(f"{self.type} action requires text")
        if self.type in {"visit_url", "navigate"} and not self.url:
            raise ValueError(f"{self.type} action requires url")
        if self.type in {"web_search", "search"} and not self.query:
            raise ValueError(f"{self.type} action requires query")
        if self.type == "scroll":
            if self.scroll_dx is None and self.scroll_dy is None:
                # scroll can be up/down/left/right without dx/dy if using browser_use style
                pass
        if self.type in {"keypress", "send_keys"} and not self.keys:
            raise ValueError(f"{self.type} action requires keys")
        if self.type == "wait" and self.seconds is None:
            raise ValueError("wait action requires seconds")
        if self.type == "upload_file" and (self.index is None or not self.path):
            raise ValueError("upload_file requires index and path")
        if self.type == "evaluate" and not self.script:
            raise ValueError("evaluate requires script")

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"type": self.type}
        for key in (
            "x",
            "y",
            "index",
            "button",
            "text",
            "url",
            "query",
            "scroll_dx",
            "scroll_dy",
            "keys",
            "seconds",
            "path",
            "script",
        ):
            value = getattr(self, key)
            if value is not None:
                data[key] = value
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ComputerCallAction":
        return cls(
            type=str(raw.get("type") or ""),
            x=raw.get("x"),
            y=raw.get("y"),
            index=raw.get("index"),
            button=raw.get("button"),
            text=raw.get("text"),
            url=raw.get("url"),
            query=raw.get("query"),
            scroll_dx=raw.get("scroll_dx"),
            scroll_dy=raw.get("scroll_dy"),
            keys=list(raw.get("keys")) if raw.get("keys") is not None else None,
            seconds=raw.get("seconds"),
            path=raw.get("path"),
            script=raw.get("script"),
        )



@dataclass(slots=True)
class ComputerCallMeta:
    reasoning_summary: str | None = None
    done: bool = False
    critical_point: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "done": bool(self.done),
            "critical_point": bool(self.critical_point),
        }
        if self.reasoning_summary:
            payload["reasoning_summary"] = self.reasoning_summary
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "ComputerCallMeta":
        raw = raw or {}
        return cls(
            reasoning_summary=raw.get("reasoning_summary"),
            done=bool(raw.get("done", False)),
            critical_point=bool(raw.get("critical_point", False)),
        )


@dataclass(slots=True)
class ComputerCall:
    call_id: str
    action: ComputerCallAction
    meta: ComputerCallMeta = field(default_factory=ComputerCallMeta)
    pending_safety_checks: list[PendingSafetyCheck] = field(default_factory=list)

    def to_dict(self, *, redact_action: bool = False) -> dict[str, Any]:
        action = self.action
        action_payload = action.to_dict()
        if redact_action and action.type == "type":
            text = action_payload.get("text")
            if text:
                action_payload["text_sha256"] = hashlib.sha256(
                    str(text).encode("utf-8")
                ).hexdigest()
                action_payload["text"] = "[REDACTED]"
        return {
            "type": "computer_call",
            "call_id": self.call_id,
            "action": action_payload,
            "meta": self.meta.to_dict(),
            "pending_safety_checks": [check.to_dict() for check in self.pending_safety_checks],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ComputerCall":
        action = ComputerCallAction.from_dict(raw.get("action") or {})
        meta = ComputerCallMeta.from_dict(raw.get("meta"))
        pending = [
            PendingSafetyCheck.from_dict(item)
            for item in (raw.get("pending_safety_checks") or [])
        ]
        return cls(call_id=str(raw.get("call_id") or ""), action=action, meta=meta, pending_safety_checks=pending)


@dataclass(slots=True)
class ExecutionResult:
    status: str
    error_type: str | None = None
    error_message: str | None = None
    captcha_detected: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"status": self.status}
        if self.error_type:
            payload["error_type"] = self.error_type
        if self.error_message:
            payload["error_message"] = self.error_message
        if self.captcha_detected:
            payload["captcha_detected"] = True
        return payload

    @classmethod
    def ok(cls) -> "ExecutionResult":
        return cls(status="ok")

    @classmethod
    def error(cls, error_type: str, message: str, captcha_detected: bool = False) -> "ExecutionResult":
        return cls(status="error", error_type=error_type, error_message=message, captcha_detected=captcha_detected)


@dataclass(slots=True)
class Viewport:
    w: int
    h: int

    def to_dict(self) -> dict[str, Any]:
        return {"w": int(self.w), "h": int(self.h)}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Viewport":
        return cls(w=int(raw.get("w") or 0), h=int(raw.get("h") or 0))


@dataclass(slots=True)
class ComputerCallOutput:
    call_id: str
    url: str
    viewport: Viewport
    screenshot_b64: str
    execution: ExecutionResult
    dom_tree: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "url": self.url,
            "viewport": self.viewport.to_dict(),
            "screenshot_b64": self.screenshot_b64,
            "execution": self.execution.to_dict(),
        }
        if self.dom_tree is not None:
            payload["dom_tree"] = self.dom_tree
        return {
            "type": "computer_call_output",
            "call_id": self.call_id,
            "output": payload,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ComputerCallOutput":
        output = raw.get("output") or {}
        return cls(
            call_id=str(raw.get("call_id") or ""),
            url=str(output.get("url") or ""),
            viewport=Viewport.from_dict(output.get("viewport") or {}),
            screenshot_b64=str(output.get("screenshot_b64") or ""),
            execution=ExecutionResult(
                status=str((output.get("execution") or {}).get("status") or "ok"),
                error_type=(output.get("execution") or {}).get("error_type"),
                error_message=(output.get("execution") or {}).get("error_message"),
                captcha_detected=bool((output.get("execution") or {}).get("captcha_detected", False)),
            ),
            dom_tree=output.get("dom_tree"),
        )



@dataclass(slots=True)
class AcknowledgedSafetyChecks:
    acknowledged: list[str]
    decision: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "acknowledged_safety_checks",
            "acknowledged": list(self.acknowledged),
            "decision": self.decision,
        }


@dataclass(slots=True)
class DecisionRequest:
    goal: str
    observation: ComputerCallOutput
    history: list[dict[str, Any]]
    policy_summary: dict[str, Any]
    previous_response_id: str | None = None
    step_index: int = 0


@dataclass(slots=True)
class DecisionResponse:
    response_id: str
    computer_call: ComputerCall
    reasoning_summary: str | None = None


def ensure_call_id(call: ComputerCall) -> ComputerCall:
    if not call.call_id:
        call.call_id = new_call_id()
    return call


def ensure_response_id(value: str | None) -> str:
    return value or new_response_id()


def check_pending_ids(checks: Iterable[PendingSafetyCheck]) -> list[str]:
    return [check.id for check in checks if check.id]
