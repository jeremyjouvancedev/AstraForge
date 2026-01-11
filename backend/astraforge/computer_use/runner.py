from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from .decision_providers import DecisionProvider, build_policy_summary
from .policy import PolicyConfig, PolicyDecision, evaluate_policy, is_domain_allowed
from .protocol import (
    ComputerCall,
    ComputerCallOutput,
    DecisionRequest,
    ExecutionResult,
    Viewport,
    ensure_call_id,
    new_response_id,
    new_step_id,
)
from .trace import TraceWriter


class BrowserAdapter(Protocol):
    def observe(self) -> ComputerCallOutput:  # pragma: no cover - protocol
        ...

    def act(self, call: ComputerCall) -> ComputerCallOutput:  # pragma: no cover - protocol
        ...


@dataclass(slots=True)
class RunState:
    step_index: int = 0
    previous_response_id: str | None = None
    pending_call: dict[str, Any] | None = None
    pending_checks: list[dict[str, Any]] = field(default_factory=list)
    pending_step_id: str | None = None
    pending_response_id: str | None = None
    failure_count: int = 0
    last_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "previous_response_id": self.previous_response_id,
            "pending_call": self.pending_call,
            "pending_checks": self.pending_checks,
            "pending_step_id": self.pending_step_id,
            "pending_response_id": self.pending_response_id,
            "failure_count": self.failure_count,
            "last_url": self.last_url,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "RunState":
        raw = raw or {}
        return cls(
            step_index=int(raw.get("step_index") or 0),
            previous_response_id=raw.get("previous_response_id"),
            pending_call=raw.get("pending_call"),
            pending_checks=list(raw.get("pending_checks") or []),
            pending_step_id=raw.get("pending_step_id"),
            pending_response_id=raw.get("pending_response_id"),
            failure_count=int(raw.get("failure_count") or 0),
            last_url=raw.get("last_url"),
        )


@dataclass(slots=True)
class RunnerConfig:
    max_steps: int = 25
    max_runtime_seconds: int = 300
    failure_threshold: int = 3
    redact_typed_text: bool = True


@dataclass(slots=True)
class RunResult:
    status: str
    stop_reason: str | None = None
    pending_checks: list[dict[str, Any]] = field(default_factory=list)


class ComputerUseRunner:
    def __init__(
        self,
        *,
        decision_provider: DecisionProvider,
        browser: BrowserAdapter,
        policy_config: PolicyConfig,
        runner_config: RunnerConfig,
        trace: TraceWriter,
    ) -> None:
        self._decision_provider = decision_provider
        self._browser = browser
        self._policy_config = policy_config
        self._runner_config = runner_config
        self._trace = trace

    def run(self, goal: str, state: RunState) -> tuple[RunResult, RunState]:
        start = time.monotonic()
        observation: ComputerCallOutput | None = None

        if state.pending_call:
            observation = self._resume_pending_action(state)
            if observation is None:
                return RunResult(status="execution_error", stop_reason="execution_error"), state
            if state.failure_count >= self._runner_config.failure_threshold:
                return RunResult(status="execution_error", stop_reason="execution_error"), state

        if observation is None:
            observation = self._browser.observe()

        while True:
            if self._runner_config.max_steps and state.step_index >= self._runner_config.max_steps:
                return RunResult(status="max_steps", stop_reason="max_steps"), state
            if self._runner_config.max_runtime_seconds:
                if time.monotonic() - start > self._runner_config.max_runtime_seconds:
                    return RunResult(status="timed_out", stop_reason="timed_out"), state

            decision = self._decide(goal, observation, state)
            response_id = decision.response_id or new_response_id()
            call = ensure_call_id(decision.computer_call)
            call.action.validate()
            if decision.reasoning_summary and not call.meta.reasoning_summary:
                call.meta.reasoning_summary = decision.reasoning_summary

            call_dict = call.to_dict(redact_action=self._runner_config.redact_typed_text)
            self._trace.append_item(call_dict)

            policy = evaluate_policy(call, self._policy_config)
            self._trace.append_item(policy.to_item())

            if policy.decision == "block":
                return RunResult(status="blocked_policy", stop_reason="blocked_policy"), state
            if policy.decision == "require_ack":
                state.pending_call = call.to_dict(redact_action=False)
                state.pending_checks = [check.to_dict() for check in policy.checks]
                state.pending_step_id = new_step_id()
                state.pending_response_id = response_id
                return (
                    RunResult(
                        status="awaiting_ack",
                        stop_reason=None,
                        pending_checks=state.pending_checks,
                    ),
                    state,
                )

            output = self._browser.act(call)
            self._trace.append_item(output.to_dict())
            step_id = new_step_id()
            self._trace.write_step(
                step_index=state.step_index + 1,
                step_id=step_id,
                call=call,
                output=output,
                response_id=response_id,
                redact_action=self._runner_config.redact_typed_text,
            )

            state.step_index += 1
            state.previous_response_id = response_id
            state.last_url = output.url

            if output.execution.status != "ok":
                state.failure_count += 1
            else:
                state.failure_count = 0

            if state.failure_count >= self._runner_config.failure_threshold:
                return RunResult(status="execution_error", stop_reason="execution_error"), state

            if call.action.type == "terminate" or call.meta.done:
                return RunResult(status="completed", stop_reason="completed"), state

            if output.url and not is_domain_allowed(output.url, self._policy_config):
                return RunResult(status="blocked_policy", stop_reason="blocked_policy"), state

            observation = output

    def _decide(
        self,
        goal: str,
        observation: ComputerCallOutput,
        state: RunState,
    ) -> DecisionResponse:
        request = DecisionRequest(
            goal=goal,
            observation=observation,
            history=self._trace.recent_history(),
            policy_summary=build_policy_summary(asdict(self._policy_config)),
            previous_response_id=state.previous_response_id,
            step_index=state.step_index,
        )
        return self._decision_provider.decide(request)

    def _resume_pending_action(self, state: RunState) -> ComputerCallOutput | None:
        if not state.pending_call:
            return None
        try:
            call = ComputerCall.from_dict(state.pending_call)
        except Exception:
            return None
        output = self._browser.act(call)
        self._trace.append_item(output.to_dict())
        step_id = state.pending_step_id or new_step_id()
        response_id = state.pending_response_id or new_response_id()
        self._trace.write_step(
            step_index=state.step_index + 1,
            step_id=step_id,
            call=call,
            output=output,
            response_id=response_id,
            redact_action=self._runner_config.redact_typed_text,
        )
        state.step_index += 1
        state.previous_response_id = response_id
        state.pending_call = None
        state.pending_checks = []
        state.pending_step_id = None
        state.pending_response_id = None
        state.last_url = output.url
        if output.execution.status != "ok":
            state.failure_count += 1
        else:
            state.failure_count = 0
        return output


class StubBrowserAdapter:
    def __init__(self) -> None:
        self._last_url = "about:blank"

    def observe(self) -> ComputerCallOutput:
        return ComputerCallOutput(
            call_id="observe",
            url=self._last_url,
            viewport=Viewport(w=1280, h=720),
            screenshot_b64="",
            execution=ExecutionResult.ok(),
        )

    def act(self, call: ComputerCall) -> ComputerCallOutput:
        if call.action.type in ("visit_url", "navigate") and call.action.url:
            self._last_url = call.action.url
        return ComputerCallOutput(
            call_id=call.call_id,
            url=self._last_url,
            viewport=Viewport(w=1280, h=720),
            screenshot_b64="",
            execution=ExecutionResult.ok(),
        )

