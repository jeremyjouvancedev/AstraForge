from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from django.utils import timezone

from astraforge.sandbox.models import SandboxSession
from astraforge.sandbox.services import SandboxOrchestrator, SandboxProvisionError

from .browser import BrowserConfig, SandboxPlaywrightAdapter
from .decision_providers import DecisionProvider, DeepAgentDecisionProvider, ScriptedDecisionProvider, normalize_script
from .policy import PolicyConfig
from .protocol import AcknowledgedSafetyChecks
from .runner import ComputerUseRunner, RunResult, RunState, RunnerConfig
from .trace import TraceStore


def _env_list(name: str, default: list[str] | None = None) -> list[str]:
    raw = os.getenv(name, "")
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    return default or []


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _coerce_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _build_policy_config(config: dict[str, Any]) -> PolicyConfig:
    approval_mode = str(
        config.get("approval_mode") or os.getenv("COMPUTER_USE_APPROVAL_MODE", "auto")
    ).strip().lower()
    if approval_mode not in {"auto", "on_risk", "always"}:
        approval_mode = "auto"
    if "allowed_domains" in config:
        allowed_domains = _coerce_list(config.get("allowed_domains"))
    else:
        allowed_domains = _coerce_list(_env_list("COMPUTER_USE_ALLOWED_DOMAINS"))
    if "blocked_domains" in config:
        blocked_domains = _coerce_list(config.get("blocked_domains"))
    else:
        blocked_domains = _coerce_list(_env_list("COMPUTER_USE_BLOCKED_DOMAINS"))
    return PolicyConfig(
        allowed_domains=allowed_domains,
        blocked_domains=blocked_domains,
        approval_mode=approval_mode,
        allow_login=bool(config.get("allow_login", _env_bool("COMPUTER_USE_ALLOW_LOGIN", False))),
        allow_payments=bool(config.get("allow_payments", _env_bool("COMPUTER_USE_ALLOW_PAYMENTS", False))),
        allow_irreversible=bool(
            config.get("allow_irreversible", _env_bool("COMPUTER_USE_ALLOW_IRREVERSIBLE", False))
        ),
        allow_credentials=bool(
            config.get("allow_credentials", _env_bool("COMPUTER_USE_ALLOW_CREDENTIALS", False))
        ),
        default_deny=bool(config.get("default_deny", _env_bool("COMPUTER_USE_DEFAULT_DENY", True))),
        prompt_injection_detection=bool(
            config.get(
                "prompt_injection_detection",
                _env_bool("COMPUTER_USE_PROMPT_INJECTION_DETECTION", True),
            )
        ),
    )


def _build_runner_config(config: dict[str, Any]) -> RunnerConfig:
    return RunnerConfig(
        max_steps=int(config.get("max_steps") or _env_int("COMPUTER_USE_MAX_STEPS", 25)),
        max_runtime_seconds=int(
            config.get("max_runtime_seconds")
            or _env_int("COMPUTER_USE_MAX_RUNTIME_SECONDS", 300)
        ),
        failure_threshold=int(
            config.get("failure_threshold") or _env_int("COMPUTER_USE_FAILURE_THRESHOLD", 3)
        ),
        redact_typed_text=bool(
            config.get("redact_typed_text", _env_bool("COMPUTER_USE_REDACT_TYPED_TEXT", True))
        ),
    )


def _build_browser_config(config: dict[str, Any]) -> BrowserConfig:
    return BrowserConfig(
        viewport_w=int(config.get("viewport_w") or _env_int("COMPUTER_USE_VIEWPORT_W", 1280)),
        viewport_h=int(config.get("viewport_h") or _env_int("COMPUTER_USE_VIEWPORT_H", 720)),
        navigation_timeout_ms=int(
            config.get("navigation_timeout_ms")
            or _env_int("COMPUTER_USE_NAV_TIMEOUT_MS", 15000)
        ),
        action_timeout_ms=int(
            config.get("action_timeout_ms") or _env_int("COMPUTER_USE_ACTION_TIMEOUT_MS", 10000)
        ),
        wait_after_action_ms=int(
            config.get("wait_after_action_ms")
            or _env_int("COMPUTER_USE_WAIT_AFTER_ACTION_MS", 750)
        ),
        script_timeout_sec=int(
            config.get("script_timeout_sec")
            or _env_int("COMPUTER_USE_SCRIPT_TIMEOUT_SEC", 120)
        ),
    )


def _trace_root() -> Path:
    raw = os.getenv("COMPUTER_USE_TRACE_DIR", "/var/lib/astraforge/computer-use")
    return Path(raw)


def _resolve_provider(
    provider_key: str, script: list[dict[str, Any]] | None, config: dict[str, Any]
) -> DecisionProvider:
    if provider_key == "scripted":
        return ScriptedDecisionProvider(script=normalize_script(script))
    if provider_key == "deepagent":
        return DeepAgentDecisionProvider(
            provider=str(config.get("llm_provider") or os.getenv("LLM_PROVIDER") or "ollama").strip().lower(),
            model_name=str(config.get("llm_model") or os.getenv("LLM_MODEL") or "devstral-small-2:24b").strip(),
            reasoning_effort=str(config.get("reasoning_effort") or "high").strip().lower(),
            reasoning_check=bool(config.get("reasoning_check", True)),
        )
    raise ValueError(f"Unsupported decision provider '{provider_key}'")


class ComputerUseService:
    def __init__(self, *, orchestrator: SandboxOrchestrator | None = None) -> None:
        self._orchestrator = orchestrator or SandboxOrchestrator()

    def run_until_pause(
        self,
        run,
        *,
        decision_provider: str,
        decision_script: list[dict[str, Any]] | None,
    ) -> RunResult:
        decision_provider = str(decision_provider or "scripted").strip().lower()
        session = run.sandbox_session
        if session:
            self._ensure_session_ready(session)

        config = dict(run.config or {})
        policy_config = _build_policy_config(config)
        runner_config = _build_runner_config(config)
        browser_config = _build_browser_config(config)

        try:
            history_window = int(config.get("history_window", 10))
        except (TypeError, ValueError):
            history_window = 10
        trace_store = TraceStore(_trace_root(), history_window=history_window)
        if not run.trace_dir:
            trace = trace_store.start_run(str(run.id), _build_config_snapshot(run, decision_provider))
            run.trace_dir = str(trace.run_dir)
            run.save(update_fields=["trace_dir"])
        else:
            trace = trace_store.open_run(str(run.id))

        provider = _resolve_provider(decision_provider, decision_script, config)
        browser = SandboxPlaywrightAdapter(session, policy=policy_config, config=browser_config) if session else None
        if browser is None:
            raise ValueError("Sandbox session is required for computer-use mode")

        state = RunState.from_dict(run.state)
        runner = ComputerUseRunner(
            decision_provider=provider,
            browser=browser,
            policy_config=policy_config,
            runner_config=runner_config,
            trace=trace,
        )
        result, updated_state = runner.run(run.goal, state)

        run.state = updated_state.to_dict()
        run.status = result.status
        run.stop_reason = result.stop_reason or ""
        run.updated_at = timezone.now()
        run.save(update_fields=["state", "status", "stop_reason", "trace_dir", "updated_at"])

        if result.status not in {"awaiting_ack", "running"}:
            trace.write_report(
                {
                    "status": result.status,
                    "stop_reason": result.stop_reason,
                    "steps": updated_state.step_index,
                    "last_url": updated_state.last_url,
                }
            )

        return result

    def acknowledge(self, run, *, acknowledged: list[str], decision: str) -> RunResult:
        try:
            history_window = int((run.config or {}).get("history_window", 10))
        except (TypeError, ValueError):
            history_window = 10
        trace_store = TraceStore(_trace_root(), history_window=history_window)
        trace = trace_store.open_run(str(run.id))
        trace.append_item(AcknowledgedSafetyChecks(acknowledged=acknowledged, decision=decision).to_dict())

        if decision == "deny":
            # ... (omitting for brevity in thought, but must include in replace)
            run_state = RunState.from_dict(run.state)
            run_state.pending_call = None
            run_state.pending_checks = []
            run_state.pending_step_id = None
            run_state.pending_response_id = None
            run.state = run_state.to_dict()
            run.status = run.Status.DENIED_APPROVAL
            run.stop_reason = "denied_approval"
            run.updated_at = timezone.now()
            run.save(update_fields=["state", "status", "stop_reason", "updated_at"])
            trace.write_report(
                {
                    "status": run.status,
                    "stop_reason": run.stop_reason,
                    "steps": RunState.from_dict(run.state).step_index,
                }
            )
            return RunResult(status=run.status, stop_reason=run.stop_reason)

        return self.run_until_pause(
            run,
            decision_provider=str(run.config.get("decision_provider") or "scripted"),
            decision_script=run.config.get("decision_script"),
        )

    def _ensure_session_ready(self, session: SandboxSession) -> None:
        if session.status == SandboxSession.Status.READY:
            return
        try:
            self._orchestrator.provision(session)
        except SandboxProvisionError as exc:
            raise ValueError(f"Sandbox session not ready: {exc}") from exc


def _build_config_snapshot(run, decision_provider: str) -> dict[str, Any]:
    snapshot = {
        "goal": run.goal,
        "decision_provider": decision_provider,
        "config": dict(run.config or {}),
    }
    if run.sandbox_session:
        snapshot["sandbox_session_id"] = str(run.sandbox_session_id)
    return snapshot
