from __future__ import annotations

from astraforge.computer_use.decision_providers import ScriptedDecisionProvider
from astraforge.computer_use.policy import PolicyConfig
from astraforge.computer_use.protocol import ComputerCall, ComputerCallAction
from astraforge.computer_use.runner import (
    ComputerUseRunner,
    RunState,
    RunnerConfig,
    StubBrowserAdapter,
)
from astraforge.computer_use.trace import TraceStore


def _build_runner(tmp_path, *, script, policy_config=None):
    provider = ScriptedDecisionProvider(script=script)
    browser = StubBrowserAdapter()
    policy_config = policy_config or PolicyConfig(allowed_domains=["example.com"], default_deny=True)
    runner_config = RunnerConfig(max_steps=5, max_runtime_seconds=30, failure_threshold=2)
    trace = TraceStore(tmp_path, history_window=5).start_run("run-1", {"goal": "test"})
    return ComputerUseRunner(
        decision_provider=provider,
        browser=browser,
        policy_config=policy_config,
        runner_config=runner_config,
        trace=trace,
    )


def test_runner_completes_with_scripted_actions(tmp_path):
    script = [
        {"action": {"type": "visit_url", "url": "https://example.com"}},
        {"action": {"type": "terminate"}},
    ]
    runner = _build_runner(tmp_path, script=script)

    result, state = runner.run("goal", RunState())

    assert result.status == "completed"
    assert state.step_index == 2

    timeline = (tmp_path / "run-1" / "timeline.jsonl").read_text().splitlines()
    assert any("computer_call" in line for line in timeline)
    assert any("computer_call_output" in line for line in timeline)
    assert (tmp_path / "run-1" / "steps" / "0001.json").exists()


def test_runner_requires_ack_for_credentials(tmp_path):
    script = [
        {
            "action": {
                "type": "type",
                "x": 10,
                "y": 20,
                "text": "password123",
            }
        }
    ]
    policy_config = PolicyConfig(allowed_domains=["example.com"], default_deny=True)
    runner = _build_runner(tmp_path, script=script, policy_config=policy_config)

    result, state = runner.run("goal", RunState())

    assert result.status == "awaiting_ack"
    assert state.pending_call is not None
    assert state.pending_checks


def test_runner_blocks_disallowed_domain(tmp_path):
    script = [{"action": {"type": "visit_url", "url": "https://evil.com"}}]
    policy_config = PolicyConfig(allowed_domains=["example.com"], default_deny=True)
    runner = _build_runner(tmp_path, script=script, policy_config=policy_config)

    result, _ = runner.run("goal", RunState())

    assert result.status == "blocked_policy"


def test_runner_resumes_pending_action(tmp_path):
    script = [{"action": {"type": "terminate"}}]
    runner = _build_runner(tmp_path, script=script)

    pending_call = ComputerCall(
        call_id="call-1",
        action=ComputerCallAction(type="visit_url", url="https://example.com"),
    ).to_dict(redact_action=False)
    state = RunState(
        pending_call=pending_call,
        pending_response_id="resp-1",
        pending_step_id="step-1",
    )

    result, updated = runner.run("goal", state)

    assert result.status == "completed"
    assert updated.step_index == 2
