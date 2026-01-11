from __future__ import annotations

import base64
import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .protocol import ComputerCall, ComputerCallOutput


@dataclass(slots=True)
class TraceWriter:
    run_dir: Path
    timeline_path: Path
    steps_dir: Path
    replay_dir: Path
    history_window: int = 10
    _history: deque[dict[str, Any]] = field(init=False, repr=False)
    _replay_actions_path: Path = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._history = deque(maxlen=self.history_window)
        self._replay_actions_path = self.replay_dir / "actions.jsonl"

    def append_item(self, item: dict[str, Any]) -> None:
        payload = json.dumps(item, ensure_ascii=True)
        with self.timeline_path.open("a", encoding="utf-8") as handle:
            handle.write(payload + "\n")
        self._history.append(item)
        if item.get("type") == "computer_call":
            with self._replay_actions_path.open("a", encoding="utf-8") as handle:
                handle.write(payload + "\n")

    def recent_history(self) -> list[dict[str, Any]]:
        return list(self._history)

    def seed_history(self, items: list[dict[str, Any]]) -> None:
        self._history.clear()
        for item in items[-self.history_window :]:
            self._history.append(item)

    def write_step(
        self,
        *,
        step_index: int,
        step_id: str,
        call: ComputerCall,
        output: ComputerCallOutput,
        response_id: str,
        redact_action: bool = False,
    ) -> None:
        filename = f"{step_index:04d}"
        screenshot_path = self.steps_dir / f"{filename}.png"
        json_path = self.steps_dir / f"{filename}.json"

        if output.screenshot_b64:
            data = base64.b64decode(output.screenshot_b64.encode("ascii"))
            screenshot_path.write_bytes(data)

        payload = {
            "step_id": step_id,
            "step_index": step_index,
            "call_id": call.call_id,
            "response_id": response_id,
            "action": call.to_dict(redact_action=redact_action)["action"],
            "meta": call.meta.to_dict(),
            "pending_safety_checks": [
                check.to_dict() for check in call.pending_safety_checks
            ],
            "output_url": output.url,
            "output_viewport": output.viewport.to_dict(),
            "execution": output.execution.to_dict(),
            "screenshot_path": str(screenshot_path.name),
        }
        json_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    def write_report(self, report: dict[str, Any]) -> None:
        lines = ["# Computer-Use Run Report", ""]
        status = report.get("status") or "unknown"
        reason = report.get("stop_reason") or ""
        lines.append(f"Status: {status}")
        if reason:
            lines.append(f"Stop reason: {reason}")
        summary = report.get("summary")
        if summary:
            lines.extend(["", str(summary)])
        if report.get("last_url"):
            lines.append(f"Last URL: {report['last_url']}")
        if report.get("steps") is not None:
            lines.append(f"Steps: {report['steps']}")
        if report.get("error"):
            lines.append(f"Error: {report['error']}")
        report_path = self.run_dir / "report.md"
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@dataclass(slots=True)
class TraceStore:
    root_dir: Path
    history_window: int = 10

    def start_run(self, run_id: str, config_snapshot: dict[str, Any]) -> TraceWriter:
        run_dir = self.root_dir / run_id
        timeline_path = run_dir / "timeline.jsonl"
        steps_dir = run_dir / "steps"
        replay_dir = run_dir / "replay"
        run_dir.mkdir(parents=True, exist_ok=True)
        steps_dir.mkdir(parents=True, exist_ok=True)
        replay_dir.mkdir(parents=True, exist_ok=True)

        timeline_path.write_text("", encoding="utf-8")
        (replay_dir / "actions.jsonl").write_text("", encoding="utf-8")
        (run_dir / "config.json").write_text(
            json.dumps(config_snapshot, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        (replay_dir / "README.md").write_text(
            "Replay package for computer-use actions.\n"
            "Use actions.jsonl with the replay runner to re-execute steps.\n"
            "Example:\n"
            "python -m astraforge.computer_use.replay "
            "--trace-dir .. "
            "--sandbox-session-id <SANDBOX_SESSION_ID>\n",
            encoding="utf-8",
        )
        run_sh = replay_dir / "run.sh"
        run_sh.write_text(
            "#!/bin/sh\n"
            "python -m astraforge.computer_use.replay "
            "--trace-dir .. "
            "--sandbox-session-id \"$1\"\n",
            encoding="utf-8",
        )
        try:
            run_sh.chmod(0o755)
        except OSError:
            pass

        return TraceWriter(
            run_dir=run_dir,
            timeline_path=timeline_path,
            steps_dir=steps_dir,
            replay_dir=replay_dir,
            history_window=self.history_window,
        )

    def open_run(self, run_id: str) -> TraceWriter:
        run_dir = self.root_dir / run_id
        timeline_path = run_dir / "timeline.jsonl"
        steps_dir = run_dir / "steps"
        replay_dir = run_dir / "replay"
        steps_dir.mkdir(parents=True, exist_ok=True)
        replay_dir.mkdir(parents=True, exist_ok=True)
        if not timeline_path.exists():
            timeline_path.write_text("", encoding="utf-8")
        if not (replay_dir / "actions.jsonl").exists():
            (replay_dir / "actions.jsonl").write_text("", encoding="utf-8")
        writer = TraceWriter(
            run_dir=run_dir,
            timeline_path=timeline_path,
            steps_dir=steps_dir,
            replay_dir=replay_dir,
            history_window=self.history_window,
        )
        recent_items = _tail_jsonl(timeline_path, self.history_window)
        writer.seed_history(recent_items)
        return writer


def read_timeline_items(
    run_dir: Path,
    *,
    limit: int | None = None,
    include_screenshots: bool = True,
) -> list[dict[str, Any]]:
    timeline_path = run_dir / "timeline.jsonl"
    if not timeline_path.exists():
        return []
    if limit is not None and limit > 0:
        items = _tail_jsonl(timeline_path, limit)
    else:
        items = _read_jsonl(timeline_path)
    if not include_screenshots:
        for item in items:
            if item.get("type") != "computer_call_output":
                continue
            output = dict(item.get("output") or {})
            if "screenshot_b64" in output:
                output["screenshot_b64"] = ""
            item["output"] = output
    return items


def _tail_jsonl(path: Path, limit: int) -> list[dict[str, Any]]:
    if limit <= 0 or not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    items: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            items.append(payload)
    return items


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    items: list[dict[str, Any]] = []
    for line in lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            items.append(payload)
    return items
