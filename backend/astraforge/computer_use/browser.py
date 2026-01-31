from __future__ import annotations

import base64
import json
import os
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
        if call.action.type == "tavily_search":
            return self._run_tavily_search(call)
        return self._run_action(call, call_id=call.call_id)

    def _run_tavily_search(self, call: ComputerCall) -> ComputerCallOutput:
        query = call.action.to_dict().get("query")
        search_depth = call.action.to_dict().get("search_depth", "basic")
        
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            return ComputerCallOutput(
                call_id=call.call_id,
                url="",
                viewport=Viewport(w=self._config.viewport_w, h=self._config.viewport_h),
                screenshot_b64="",
                execution=ExecutionResult.error("tavily_error", "TAVILY_API_KEY environment variable is not set"),
            )

        import urllib.request
        import json
        import ssl

        url = "https://api.tavily.com/search"
        data = {
            "api_key": api_key,
            "query": query,
            "search_depth": search_depth,
            "include_answer": True,
            "max_results": 5
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )

            # Handle SSL verification for corporate proxy environments
            ssl_context = None
            if os.getenv("TAVILY_DISABLE_SSL_VERIFY", "0").lower() in ("1", "true", "yes"):
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
            elif os.getenv("SSL_CERT_FILE"):
                ca_bundle = os.getenv("SSL_CERT_FILE")
                if os.path.exists(ca_bundle):
                    ssl_context = ssl.create_default_context(cafile=ca_bundle)

            with urllib.request.urlopen(req, timeout=15, context=ssl_context) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                
                # Format results as a readable string for the agent
                results_text = f"Tavily Search Results for: {query}\n\n"
                if res_data.get("answer"):
                    results_text += f"Summary: {res_data['answer']}\n\n"
                
                for i, result in enumerate(res_data.get("results", [])):
                    results_text += f"[{i+1}] {result['title']}\nURL: {result['url']}\nSnippet: {result['content']}\n\n"
                
                # Skip browser observation for tavily search to save time/resources
                # The agent only needs the search results for the next decision.
                observation = ComputerCallOutput(
                    call_id=call.call_id,
                    url="about:blank", # Search doesn't change browser URL
                    viewport=Viewport(w=self._config.viewport_w, h=self._config.viewport_h),
                    screenshot_b64="", # No screenshot needed for search results
                    execution=ExecutionResult.ok(),
                    dom_tree=f"SEARCH RESULTS:\n{results_text}"
                )
                return observation

        except Exception as e:
            return ComputerCallOutput(
                call_id=call.call_id,
                url="",
                viewport=Viewport(w=self._config.viewport_w, h=self._config.viewport_h),
                screenshot_b64="",
                execution=ExecutionResult.error("tavily_error", str(e)),
            )

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
            "navigation_timeout_ms": self._config.navigation_timeout_ms,
            "action_timeout_ms": self._config.action_timeout_ms,
            "wait_after_action_ms": self._config.wait_after_action_ms,
        }
        payload_b64 = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
        
        # We pass the server code as a string to the client script so it can write it if needed.
        # This avoids separate upload steps.
        server_code_b64 = base64.b64encode(_SERVER_SCRIPT_BODY.encode("utf-8")).decode("ascii")
        
        script = _render_script(payload_b64, server_code_b64)
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
        if output is None:
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
            dom_tree=output.get("dom_tree"),
        )


def _render_script(payload_b64: str, server_code_b64: str) -> str:
    quoted_payload = shlex.quote(payload_b64)
    quoted_server = shlex.quote(server_code_b64)
    return f"env ASTRAFORGE_BROWSER_PAYLOAD={quoted_payload} ASTRAFORGE_BROWSER_SERVER_CODE_B64={quoted_server} python - <<'PY'\n{_CLIENT_SCRIPT_BODY}\nPY"

def _parse_payload(stdout: str) -> dict[str, Any] | None:
    if not stdout:
        return None

    # First attempt: Try parsing the entire stdout (handles pretty-printed or clean JSON)
    try:
        payload = json.loads(stdout.strip())
        if isinstance(payload, dict) and "output" in payload:
            return payload.get("output")
    except json.JSONDecodeError:
        pass

    # Second attempt: Line-by-line (handles mixed output/debug logs)
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


_CLIENT_SCRIPT_BODY = r"""
import os
import json
import time
import base64
import urllib.request
import urllib.error
import subprocess
import sys

payload = json.loads(base64.b64decode(os.environ.get("ASTRAFORGE_BROWSER_PAYLOAD", "")).decode("utf-8"))
SERVER_PORT = 8500
SERVER_URL = f"http://localhost:{SERVER_PORT}"
SERVER_FILE = "browser_server.py"

def is_server_running():
    try:
        with urllib.request.urlopen(f"{SERVER_URL}/health", timeout=1) as response:
            return response.status == 200
    except Exception:
        return False

if not is_server_running():
    # Write server script if it doesn't exist or we want to ensure it's fresh
    # For now, we only write if not running, to update it we'd need a version check or force restart.
    # Assuming persistent container means code persists too, but we can overwrite safely.
    server_code_b64 = os.environ.get("ASTRAFORGE_BROWSER_SERVER_CODE_B64", "")
    if server_code_b64:
        with open(SERVER_FILE, "wb") as f:
            f.write(base64.b64decode(server_code_b64))
        
    # Start server in background
    # We use nohup equivalent to ensure it survives this script's exit
    subprocess.Popen(
        [sys.executable, SERVER_FILE], 
        stdout=open("browser_server.out", "a"), 
        stderr=subprocess.STDOUT,
        close_fds=True,
        start_new_session=True
    )
    
    # Wait for startup (up to 15s)
    for _ in range(30):
        if is_server_running():
            break
        time.sleep(0.5)
    else:
        # Try to read the error log if it exists
        error_detail = ""
        try:
            if os.path.exists("browser_server.out"):
                with open("browser_server.out", "r") as f:
                    error_detail = "\nServer log:\n" + f.read()
        except:
            pass
        print(json.dumps({"output": {"execution": {"status": "error", "error_message": f"Browser server failed to start. {error_detail}"}}}))
        sys.exit(0)

# Send payload
req = urllib.request.Request(
    f"{SERVER_URL}/execute", 
    data=json.dumps(payload).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)

try:
    with urllib.request.urlopen(req, timeout=300) as response:
        print(response.read().decode('utf-8'))
    sys.stdout.flush()
    sys.exit(0)
except urllib.error.HTTPError as e:
    err_msg = e.read().decode('utf-8')
    print(json.dumps({"output": {"execution": {"status": "error", "error_message": f"Server error {e.code}: {err_msg}"}}}))
except Exception as e:
    error_detail = ""
    try:
        if os.path.exists("browser_server.out"):
            with open("browser_server.out", "r") as f:
                error_detail = "\nServer log:\n" + f.read()
    except:
        pass
    print(json.dumps({"output": {"execution": {"status": "error", "error_message": f"Connection error: {str(e)} {error_detail}"}}}))
"""

_SERVER_SCRIPT_BODY = r"""
import base64
import json
import os
import sys
import time
import http.server
import socketserver
import threading
from urllib.parse import urlparse

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("CRITICAL ERROR: 'playwright' package is not installed in the sandbox. Check Dockerfile and requirements.")
    sys.stdout.flush()
    sys.exit(1)

PORT = 8500

# Global state
PLAYWRIGHT = None
BROWSER_CONTEXT = None
PAGE = None
LAST_CONFIG = {}

SAFE_SCHEMES = {"about", "data", "file", "chrome", "blob"}

def domain_matches(hostname: str, domain: str) -> bool:
    if not hostname or not domain:
        return False
    if hostname == domain:
        return True
    return hostname.endswith("." + domain)

def is_allowed(url: str, allowed_domains, blocked_domains, default_deny) -> bool:
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

INDEX_SCRIPT = r'''() => { 
    const elements = []; 
    let index = 0; 
    const isVisible = (el) => { 
        if (!el.offsetParent && el.tagName !== 'BODY' && el.tagName !== 'HTML') return false; 
        const style = window.getComputedStyle(el); 
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false; 
        const rect = el.getBoundingClientRect(); 
        return rect.width > 0 && rect.height > 0; 
    }; 
    const INTERACTIVE_ROLES = new Set(['button', 'link', 'checkbox', 'radio', 'switch', 'textbox', 'searchbox', 'combobox', 'listbox', 'option', 'menuitem', 'menuitemcheckbox', 'menuitemradio', 'tab', 'treeitem', 'slider', 'spinbutton']); 
    const getInteractiveRole = (el) => { 
        const role = (el.getAttribute('role') || '').toLowerCase(); 
        if (role && INTERACTIVE_ROLES.has(role)) return role; 
        const tag = el.tagName.toLowerCase(); 
        if (tag === 'a') return 'link'; 
        if (tag === 'button') return 'button'; 
        if (tag === 'input') { 
            const inputType = (el.type || 'text').toLowerCase(); 
            if (inputType === 'hidden') return null; 
            if (inputType === 'submit' || inputType === 'reset' || inputType === 'button') return 'button'; 
            return inputType; 
        } 
        if (tag === 'select') return 'combobox'; 
        if (tag === 'textarea' || el.isContentEditable) return 'textbox'; 
        return null; 
    }; 
    document.querySelectorAll('.astraforge-label').forEach(el => el.remove()); 
    document.querySelectorAll('[data-astraforge-index]').forEach(el => el.removeAttribute('data-astraforge-index')); 
    const all = document.querySelectorAll('*'); 
    all.forEach(el => { 
        const role = getInteractiveRole(el); 
        const isHeader = /^H[1-6]$/.test(el.tagName); 
        if (isVisible(el) && (role || isHeader)) { 
            const rect = el.getBoundingClientRect(); 
            const elementIndex = index++; 
            let text = ''; 
            if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') { 
                text = el.value || el.placeholder || ''; 
            } else { 
                text = el.innerText || ''; 
            } 
            text = text.trim().replace(/\s+/g, ' ').substring(0, 60); 
            elements.push({ index: elementIndex, tagName: el.tagName, text: text, role: role || 'text' }); 
            el.setAttribute('data-astraforge-index', elementIndex); 
            const label = document.createElement('span'); 
            label.className = 'astraforge-label'; 
            label.style.position = 'absolute'; 
            label.style.backgroundColor = 'yellow'; 
            label.style.color = 'black'; 
            label.style.fontSize = '12px'; 
            label.style.padding = '2px'; 
            label.style.border = '1px solid black'; 
            label.style.zIndex = '999999'; 
            label.innerText = elementIndex; 
            label.style.top = (rect.top + window.scrollY) + 'px'; 
            label.style.left = (rect.left + window.scrollX) + 'px'; 
            document.body.appendChild(label); 
        } 
    }); 
    return elements; 
}'''

CAPTCHA_DETECTION_SCRIPT = r'''() => { 
    const selectors = ['iframe[src*="recaptcha"]', 'iframe[src*="hcaptcha"]', 'iframe[src*="turnstile"]', '.g-recaptcha', '#h-captcha', '#challenge-form', 'text=Verify you are human', "text=I'm not a robot", 'text=Cloudflare']; 
    for (const selector of selectors) { 
        if (selector.startsWith('text=')) { 
            const text = selector.substring(5); 
            if (document.body.innerText.includes(text)) return true; 
        } else { 
            if (document.querySelector(selector)) return true; 
        } 
    } 
    return false; 
}'''

def setup_browser(config):
    global PLAYWRIGHT, BROWSER_CONTEXT, PAGE, LAST_CONFIG
    
    user_data_dir = config.get("user_data_dir") or "/workspace/.astraforge/computer_use/profile"
    viewport = config.get("viewport") or {"w": 1280, "h": 720}
    nav_timeout = int(config.get("navigation_timeout_ms") or 15000)
    action_timeout = int(config.get("action_timeout_ms") or 10000)
    
    if BROWSER_CONTEXT:
        # Check if viewport changed? For now, ignore dynamic viewport changes to avoid restart
        return

    print("DEBUG: Starting persistent browser session...", flush=True)
    sys.stdout.flush()
    os.makedirs(user_data_dir, exist_ok=True)
    
    PLAYWRIGHT = sync_playwright().start()
    
    # Check if SSL verification should be disabled for corporate proxy environments
    ignore_https_errors = os.getenv('DISABLE_SSL_VERIFY', '0').lower() in ('1', 'true', 'yes')

    BROWSER_CONTEXT = PLAYWRIGHT.chromium.launch_persistent_context(
        user_data_dir,
        headless=True,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        viewport={"width": int(viewport.get("w", 1280)), "height": int(viewport.get("h", 720))},
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        ignore_https_errors=ignore_https_errors,
    )
    BROWSER_CONTEXT.set_default_navigation_timeout(nav_timeout)
    BROWSER_CONTEXT.set_default_timeout(action_timeout)

    # Note: Route handlers need to be set up per context, but arguments change per request (allowed_domains)
    # So we'll update the route handler logic to look at the *current* request config
    # We can store the current config in a global or pass it to a factory
    
    PAGE = BROWSER_CONTEXT.pages[0] if BROWSER_CONTEXT.pages else BROWSER_CONTEXT.new_page()
    
    # Restore last URL if needed?
    # Logic from original script: load state.json.
    state_path = config.get("state_path")
    if state_path and os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as handle:
                state = json.load(handle) or {}
                last_url = state.get("last_url")
                if last_url and last_url != "about:blank":
                    try:
                        PAGE.goto(last_url, wait_until="domcontentloaded")
                    except Exception:
                        pass
        except Exception:
            pass

def execute_action(payload):
    global PAGE, BROWSER_CONTEXT
    
    try:
        setup_browser(payload)
    except Exception as exc:
        return {
            "url": "",
            "viewport": payload.get("viewport") or {"w": 1280, "h": 720},
            "screenshot_b64": "",
            "dom_tree": "",
            "execution": {
                "status": "error",
                "error_type": "browser_init_error",
                "error_message": f"Failed to initialize browser: {str(exc)}",
            },
        }

    action = payload.get("action") or {}
    state_path = payload.get("state_path") or "/workspace/.astraforge/computer_use/state.json"
    storage_state_path = payload.get("storage_state_path")
    viewport = payload.get("viewport") or {"w": 1280, "h": 720}
    allowed_domains = [str(item or "").lower().lstrip(".") for item in (payload.get("allowed_domains") or [])]
    blocked_domains = [str(item or "").lower().lstrip(".") for item in (payload.get("blocked_domains") or [])]
    default_deny = bool(payload.get("default_deny", True))
    wait_after_action = int(payload.get("wait_after_action_ms") or 0)

    # Dynamic Route Handler Update
    # Since we have one persistent context, we need to ensure the route handler uses the LATEST allowed/blocked domains.
    # The route handler is registered once. We can use a mutable object or closure to access current config.
    
    # Actually, we can unroute and reroute? Or just use a global "current_policy" variable.
    global CURRENT_POLICY
    CURRENT_POLICY = {
        "allowed": allowed_domains, 
        "blocked": blocked_domains, 
        "default_deny": default_deny
    }
    
    # Ensure route handler is registered once
    if not getattr(BROWSER_CONTEXT, "_has_route_handler", False):
        def route_handler(route, request):
            allowed = CURRENT_POLICY["allowed"]
            blocked = CURRENT_POLICY["blocked"]
            deny = CURRENT_POLICY["default_deny"]
            
            if is_allowed(request.url, allowed, blocked, deny):
                route.continue_()
            else:
                # We can track blocked URLs if needed, but for now just abort
                route.abort("blockedbyclient")
        BROWSER_CONTEXT.route("**/*", route_handler)
        BROWSER_CONTEXT._has_route_handler = True

    output = {
        "url": "",
        "viewport": viewport,
        "screenshot_b64": "",
        "dom_tree": "",
        "execution": {"status": "ok"},
    }

    try:
        page = PAGE
        action_type = action.get("type")

        if action.get("index") is not None:
            page.evaluate(INDEX_SCRIPT)

        def get_element_by_index(idx):
            if idx is None:
                return None
            return page.query_selector(f'[data-astraforge-index="{idx}"]')

        if action_type in ("visit_url", "navigate") and action.get("url"):
            page.goto(action["url"], wait_until="domcontentloaded")
        elif action_type == "click":
            idx = action.get("index")
            if idx is not None:
                el = get_element_by_index(idx)
                if el:
                    el.scroll_into_view_if_needed()
                    try:
                        el.click(timeout=3000)
                        print("DEBUG: Standard click successful")
                    except Exception as e1:
                        print(f"DEBUG: Standard click failed: {e1}")
                        try:
                            el.click(force=True)
                            print("DEBUG: Force click successful")
                        except Exception as e2:
                            print(f"DEBUG: Force click failed: {e2}")
                            el.evaluate("element => element.click()")
                            print("DEBUG: JS click successful")
                else:
                    raise ValueError(f"Element with index {idx} not found")
            else:
                x = int(action.get("x") or 0)
                y = int(action.get("y") or 0)
                page.mouse.click(x, y, button=action.get("button") or "left")
        elif action_type == "double_click":
            idx = action.get("index")
            if idx is not None:
                el = get_element_by_index(idx)
                if el:
                    el.scroll_into_view_if_needed()
                    try:
                        el.dblclick(timeout=3000)
                    except Exception:
                        el.dblclick(force=True)
                else:
                    raise ValueError(f"Element with index {idx} not found")
            else:
                x = int(action.get("x") or 0)
                y = int(action.get("y") or 0)
                page.mouse.click(x, y, button=action.get("button") or "left", click_count=2)
        elif action_type in ("type", "input"):
            idx = action.get("index")
            text = action.get("text") or ""
            submit = action.get("submit")
            if idx is not None:
                el = get_element_by_index(idx)
                if el:
                    el.scroll_into_view_if_needed()
                    try:
                        el.fill(text, timeout=3000)
                    except Exception:
                        el.click(force=True)
                        page.keyboard.type(text)
                    
                    if submit:
                        el.press("Enter")
                else:
                    raise ValueError(f"Element with index {idx} not found")
            else:
                x = int(action.get("x") or 0)
                y = int(action.get("y") or 0)
                page.mouse.click(x, y, button=action.get("button") or "left")
                page.keyboard.type(text)
                
                if submit:
                    page.keyboard.press("Enter")
        elif action_type == "scroll":
            dx = action.get("scroll_dx")
            dy = action.get("scroll_dy")
            if dx is not None or dy is not None:
                page.mouse.wheel(int(dx or 0), int(dy or 0))
            else:
                page.mouse.wheel(0, 500)
        elif action_type in ("keypress", "send_keys"):
            keys = action.get("keys") or []
            if not keys and action.get("text"):
                keys = [action.get("text")]
            mapping = {"CTRL": "Control", "CMD": "Meta", "ALT": "Alt", "SHIFT": "Shift", "ENTER": "Enter", "ESCAPE": "Escape"}
            for key in keys:
                normalized = mapping.get(key.upper(), key)
                page.keyboard.press(normalized)
        elif action_type in ("back", "go_back"):
            page.go_back()
        elif action_type == "wait":
            seconds = float(action.get("seconds") or 1.0)
            page.wait_for_timeout(int(seconds * 1000))
        elif action_type == "upload_file":
            idx = action.get("index")
            path = action.get("path")
            el = get_element_by_index(idx)
            if el:
                el.set_input_files(path)
            else:
                raise ValueError(f"Element with index {idx} not found")
        elif action_type == "find_text":
            text = action.get("text")
            page.evaluate(f"window.find('{text}')")
        elif action_type == "evaluate":
            output["script_result"] = page.evaluate(action.get("script"))
        elif action_type == "switch":
            idx = action.get("index") or 0
            if idx < len(BROWSER_CONTEXT.pages):
                PAGE = BROWSER_CONTEXT.pages[idx]
                PAGE.bring_to_front()
        elif action_type == "close":
            # Don't close the last page in persistent mode, or navigate to blank?
            # User wants persistence. But "close" means close tab.
            page.close()
            if BROWSER_CONTEXT.pages:
                PAGE = BROWSER_CONTEXT.pages[0]
            else:
                # If no pages, open new one
                PAGE = BROWSER_CONTEXT.new_page()
            # Update local handle for post-action observation
            page = PAGE
        elif action_type == "dropdown_options":
            idx = action.get("index")
            el = get_element_by_index(idx)
            if el:
                output["options"] = el.evaluate("el => Array.from(el.options).map(o => ({text: o.text, value: o.value}))")
        elif action_type == "select_dropdown":
            idx = action.get("index")
            value = action.get("text") or action.get("value")
            el = get_element_by_index(idx)
            if el:
                el.select_option(value=value)

        try:
            page.wait_for_load_state("networkidle", timeout=2000)
        except Exception:
            pass

        if wait_after_action > 0:
            page.wait_for_timeout(wait_after_action)

        captcha_detected = bool(page.evaluate(CAPTCHA_DETECTION_SCRIPT))
        elements = page.evaluate(INDEX_SCRIPT)
        output["url"] = page.url
        output["viewport"] = viewport
        output["screenshot_b64"] = base64.b64encode(page.screenshot(type="png")).decode("ascii")
        dom_lines = []
        for el in elements:
            dom_lines.append(f"[{el['index']}] {el['role']} '{el['text']}'")
        output["dom_tree"] = "\n".join(dom_lines)
        output["execution"]["captcha_detected"] = captcha_detected

        try:
            if storage_state_path:
                BROWSER_CONTEXT.storage_state(path=storage_state_path)
        except Exception:
            pass

        state = {
            "last_url": output["url"],
            "viewport": viewport
        }
        with open(state_path, "w", encoding="utf-8") as handle:
            json.dump(state, handle)

    except Exception as exc:
        msg = str(exc)
        # Check blocked list if available
        # ... (error handling logic) ...
        output["execution"] = {
            "status": "error",
            "error_type": "playwright_exception",
            "error_message": msg,
        }

    return output

class RequestHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass # Silence logs

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
    
    def do_POST(self):
        if self.path == "/execute":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            payload = json.loads(post_data.decode('utf-8'))
            
            result = execute_action(payload)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"output": result}).encode('utf-8'))

class CustomTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

if __name__ == "__main__":
    # Ensure UTF-8 stdout
    # sys.stdout.reconfigure(encoding='utf-8') 
    print(f"DEBUG: Browser server starting on port {PORT} using {sys.executable}...", flush=True)
    sys.stdout.flush()
    with CustomTCPServer(("0.0.0.0", PORT), RequestHandler) as httpd:
        print(f"Listening on port {PORT}")
        httpd.serve_forever()
"""