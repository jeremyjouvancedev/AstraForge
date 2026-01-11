from __future__ import annotations

import base64
import json
import shlex
from dataclasses import dataclass
from typing import Any

from astraforge.sandbox.models import SandboxSession
from astraforge.sandbox.services import SandboxOrchestrator, SandboxProvisionError

from .policy import PolicyConfig
from .protocol import ComputerCall, ComputerCallOutput, ExecutionResult, Viewport


@dataclass(slots=True)
class BrowserConfig:
    viewport_w: int = 1280
    viewport_h: int = 720
    navigation_timeout_ms: int = 15000
    action_timeout_ms: int = 10000
    wait_after_action_ms: int = 750
    script_timeout_sec: int = 120


class SandboxPlaywrightAdapter:
    def __init__(
        self,
        session: SandboxSession,
        *,
        policy: PolicyConfig,
        config: BrowserConfig | None = None,
        orchestrator: SandboxOrchestrator | None = None,
    ) -> None:
        self._session = session
        self._policy = policy
        self._config = config or BrowserConfig()
        self._orchestrator = orchestrator or SandboxOrchestrator()
        workspace = session.workspace_path or "/workspace"
        base_dir = f"{workspace.rstrip('/')}/.astraforge/computer_use"
        self._state_path = f"{base_dir}/state.json"
        self._profile_dir = f"{base_dir}/profile"
        self._storage_state_path = f"{base_dir}/storage_state.json"

    def observe(self) -> ComputerCallOutput:
        return self._run_action(None, call_id="observe")

    def act(self, call: ComputerCall) -> ComputerCallOutput:
        return self._run_action(call, call_id=call.call_id)

    def _run_action(self, call: ComputerCall | None, *, call_id: str) -> ComputerCallOutput:
        payload = {
            "action": call.action.to_dict() if call else None,
            "state_path": self._state_path,
            "user_data_dir": self._profile_dir,
            "storage_state_path": self._storage_state_path,
            "viewport": {"w": self._config.viewport_w, "h": self._config.viewport_h},
            "allowed_domains": self._policy.allowed_domains,
            "blocked_domains": self._policy.blocked_domains,
            "default_deny": self._policy.default_deny,
            "search_base_url": self._policy.search_base_url,
            "search_param": self._policy.search_param,
            "navigation_timeout_ms": self._config.navigation_timeout_ms,
            "action_timeout_ms": self._config.action_timeout_ms,
            "wait_after_action_ms": self._config.wait_after_action_ms,
        }
        payload_b64 = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
        script = _render_script(payload_b64)
        try:
            result = self._orchestrator.execute(
                self._session,
                script,
                cwd=self._session.workspace_path,
                timeout_sec=self._config.script_timeout_sec,
            )
        except SandboxProvisionError as exc:
            return ComputerCallOutput(
                call_id=call_id,
                url="",
                viewport=Viewport(w=self._config.viewport_w, h=self._config.viewport_h),
                screenshot_b64="",
                execution=ExecutionResult.error("sandbox_error", str(exc)),
            )

        output = _parse_payload(result.stdout or "")
        if output is None or result.exit_code != 0:
            message = (result.stdout or result.stderr or "").strip()
            return ComputerCallOutput(
                call_id=call_id,
                url="",
                viewport=Viewport(w=self._config.viewport_w, h=self._config.viewport_h),
                screenshot_b64="",
                execution=ExecutionResult.error("playwright_error", message or "Browser action failed"),
            )

        viewport = output.get("viewport") or {}
        return ComputerCallOutput(
            call_id=call_id,
            url=str(output.get("url") or ""),
            viewport=Viewport(
                w=int(viewport.get("w") or self._config.viewport_w),
                h=int(viewport.get("h") or self._config.viewport_h),
            ),
            screenshot_b64=str(output.get("screenshot_b64") or ""),
            execution=ExecutionResult(
                status=str((output.get("execution") or {}).get("status") or "ok"),
                error_type=(output.get("execution") or {}).get("error_type"),
                error_message=(output.get("execution") or {}).get("error_message"),
            ),
        )


def _render_script(payload_b64: str) -> str:
    quoted = shlex.quote(payload_b64)
    return f"env ASTRAFORGE_BROWSER_PAYLOAD={quoted} python - <<'PY'\n{_SCRIPT_BODY}\nPY"


def _parse_payload(stdout: str) -> dict[str, Any] | None:
    if not stdout:
        return None
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    for line in reversed(lines):
        if not (line.startswith("{") and line.endswith("}")):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and "output" in payload:
            return payload.get("output")
    return None


_SCRIPT_BODY = r"""
import base64
import json
import os
from urllib.parse import urlencode, urlparse

from playwright.sync_api import sync_playwright

payload = json.loads(base64.b64decode(os.environ.get("ASTRAFORGE_BROWSER_PAYLOAD", "")).decode("utf-8"))

action = payload.get("action") or {}
state_path = payload.get("state_path") or "/workspace/.astraforge/computer_use/state.json"
user_data_dir = payload.get("user_data_dir") or "/workspace/.astraforge/computer_use/profile"
storage_state_path = payload.get("storage_state_path")
viewport = payload.get("viewport") or {"w": 1280, "h": 720}
allowed_domains = [str(item or "").lower().lstrip(".") for item in (payload.get("allowed_domains") or [])]
blocked_domains = [str(item or "").lower().lstrip(".") for item in (payload.get("blocked_domains") or [])]
default_deny = bool(payload.get("default_deny", True))
search_base_url = payload.get("search_base_url") or "https://duckduckgo.com/"
search_param = payload.get("search_param") or "q"
nav_timeout = int(payload.get("navigation_timeout_ms") or 15000)
action_timeout = int(payload.get("action_timeout_ms") or 10000)
wait_after_action = int(payload.get("wait_after_action_ms") or 0)

os.makedirs(os.path.dirname(state_path), exist_ok=True)
os.makedirs(user_data_dir, exist_ok=True)

state = {}
if os.path.exists(state_path):
    try:
        with open(state_path, "r", encoding="utf-8") as handle:
            state = json.load(handle) or {}
    except Exception:
        state = {}

last_url = state.get("last_url") or "about:blank"

SAFE_SCHEMES = {"about", "data", "file", "chrome", "blob"}


def domain_matches(hostname: str, domain: str) -> bool:
    if not hostname or not domain:
        return False
    if hostname == domain:
        return True
    return hostname.endswith("." + domain)


def is_allowed(url: str) -> bool:
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme in SAFE_SCHEMES:
        return True
    if scheme not in {"http", "https"}:
        return not default_deny
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return not default_deny
    for domain in blocked_domains:
        if domain_matches(hostname, domain):
            return False
    if not allowed_domains:
        return not default_deny
    if "*" in allowed_domains:
        return True
    return any(domain_matches(hostname, domain) for domain in allowed_domains)


output = {
    "url": "",
    "viewport": viewport,
    "screenshot_b64": "",
    "execution": {"status": "ok"},
}

try:
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir,
            headless=True,
            viewport={"width": int(viewport.get("w", 1280)), "height": int(viewport.get("h", 720))},
        )
        context.set_default_navigation_timeout(nav_timeout)
        context.set_default_timeout(action_timeout)

        def route_handler(route, request):
            if is_allowed(request.url):
                route.continue_()
            else:
                route.abort()

        context.route("**/*", route_handler)

        page = context.pages[0] if context.pages else context.new_page()
        if last_url:
            try:
                page.goto(last_url, wait_until="domcontentloaded")
            except Exception:
                pass

        action_type = action.get("type")
        if action_type == "visit_url" and action.get("url"):
            page.goto(action["url"], wait_until="domcontentloaded")
        elif action_type == "web_search" and action.get("query"):
            params = urlencode({search_param: action.get("query")})
            page.goto(f"{search_base_url}?{params}", wait_until="domcontentloaded")
        elif action_type == "click":
            x = int(action.get("x") or 0)
            y = int(action.get("y") or 0)
            page.mouse.click(x, y, button=action.get("button") or "left")
        elif action_type == "double_click":
            x = int(action.get("x") or 0)
            y = int(action.get("y") or 0)
            page.mouse.click(
                x,
                y,
                button=action.get("button") or "left",
                click_count=2,
            )
        elif action_type == "type":
            x = int(action.get("x") or 0)
            y = int(action.get("y") or 0)
            page.mouse.click(x, y, button=action.get("button") or "left")
            page.keyboard.type(action.get("text") or "")
        elif action_type == "scroll":
            page.mouse.wheel(int(action.get("scroll_dx", 0)), int(action.get("scroll_dy", 0)))
        elif action_type == "keypress":
            keys = action.get("keys") or []
            mapping = {"CTRL": "Control", "CMD": "Meta", "ALT": "Alt", "SHIFT": "Shift"}
            if keys:
                normalized = [mapping.get(key, key.title()) for key in keys]
                combo = "+".join(normalized)
                page.keyboard.press(combo)
        elif action_type == "back":
            page.go_back()
        elif action_type == "wait":
            seconds = float(action.get("seconds") or 0)
            page.wait_for_timeout(int(seconds * 1000))

        if wait_after_action > 0:
            page.wait_for_timeout(wait_after_action)

        output["url"] = page.url
        output["viewport"] = viewport
        output["screenshot_b64"] = base64.b64encode(page.screenshot(type="png")).decode("ascii")

        try:
            if storage_state_path:
                context.storage_state(path=storage_state_path)
        except Exception:
            pass

        state["last_url"] = output["url"]
        state["viewport"] = viewport
        with open(state_path, "w", encoding="utf-8") as handle:
            json.dump(state, handle)

        context.close()
except Exception as exc:
    output["execution"] = {
        "status": "error",
        "error_type": "playwright_exception",
        "error_message": str(exc),
    }

print(json.dumps({"output": output}))
"""
