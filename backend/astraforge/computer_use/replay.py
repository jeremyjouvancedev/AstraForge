from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import django

from astraforge.sandbox.models import SandboxSession
from astraforge.sandbox.services import SandboxOrchestrator, SandboxProvisionError

from .browser import SandboxPlaywrightAdapter
from .protocol import ComputerCall
from .service import _build_browser_config, _build_policy_config


def _load_actions(actions_path: Path) -> list[dict]:
    if not actions_path.exists():
        return []
    lines = actions_path.read_text(encoding="utf-8").splitlines()
    items = []
    for line in lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            items.append(payload)
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay computer-use actions")
    parser.add_argument("--trace-dir", required=True)
    parser.add_argument("--sandbox-session-id", required=True)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "astraforge.config.settings")
    django.setup()

    trace_dir = Path(args.trace_dir)
    config_path = trace_dir / "config.json"
    config_payload = {}
    if config_path.exists():
        try:
            config_payload = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            config_payload = {}

    run_config = config_payload.get("config") if isinstance(config_payload, dict) else {}
    run_config = run_config or {}

    try:
        session = SandboxSession.objects.get(id=args.sandbox_session_id)
    except SandboxSession.DoesNotExist:
        raise SystemExit("Sandbox session not found")

    if session.status != SandboxSession.Status.READY:
        try:
            SandboxOrchestrator().provision(session)
        except SandboxProvisionError as exc:
            raise SystemExit(f"Sandbox not ready: {exc}")

    policy_config = _build_policy_config(run_config)
    browser_config = _build_browser_config(run_config)
    browser = SandboxPlaywrightAdapter(session, policy=policy_config, config=browser_config)

    actions_path = trace_dir / "replay" / "actions.jsonl"
    output_path = trace_dir / "replay" / "replay_output.jsonl"
    items = _load_actions(actions_path)
    limit = args.limit if args.limit and args.limit > 0 else None

    with output_path.open("w", encoding="utf-8") as handle:
        for index, item in enumerate(items):
            if limit is not None and index >= limit:
                break
            if item.get("type") != "computer_call":
                continue
            call = ComputerCall.from_dict(item)
            output = browser.act(call)
            handle.write(json.dumps(output.to_dict(), ensure_ascii=True) + "\n")
            if call.action.type == "terminate":
                break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
