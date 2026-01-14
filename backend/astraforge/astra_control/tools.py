import os
import json
import base64
import shlex
from typing import Optional, List, Dict, Any
from langchain_core.tools import tool
from langgraph.types import interrupt
from astraforge.infrastructure.ai.tavily_tools import tavily_web_search

class SandboxToolset:
    def __init__(self, sandbox_session_id: str, validation_required: bool = True):
        self.sandbox_session_id = sandbox_session_id
        self.validation_required = validation_required
        print(f"DEBUG: Initialized SandboxToolset for session {self.sandbox_session_id} (validation: {validation_required})")

    def _get_orchestrator_and_session(self):
        from astraforge.sandbox.models import SandboxSession
        from astraforge.sandbox.services import SandboxOrchestrator
        
        session = SandboxSession.objects.get(id=self.sandbox_session_id)
        orchestrator = SandboxOrchestrator()
        
        # Ensure the container is alive before any operation
        if session.status != SandboxSession.Status.READY:
            orchestrator.provision(session)
            
        return orchestrator, session

    def run_shell(self, command: str, cwd: Optional[str] = None) -> str:
        """Execute a shell command in the Ubuntu environment."""
        # Human-in-the-loop validation
        if self.validation_required:
            answer = interrupt({
                "action": "run_shell",
                "command": command,
                "cwd": cwd,
                "description": f"Execute command: {command}"
            })
            if answer != "approve":
                return "Action cancelled by user."

        try:
            orchestrator, session = self._get_orchestrator_and_session()
            result = orchestrator.execute(session, command, cwd=cwd)
            if result.exit_code == 0:
                return f"Exit Code: 0\nStdout: {result.stdout}\nStderr: {result.stderr}"
            return f"Error (Exit Code {result.exit_code}):\nStdout: {result.stdout}\nStderr: {result.stderr}"
        except Exception as e:
            return f"System Error: {e}"

    def read_file(self, path: str) -> str:
        """Read the content of a file."""
        try:
            orchestrator, session = self._get_orchestrator_and_session()
            result = orchestrator.execute(session, f"cat {shlex.quote(path)}")
            if result.exit_code == 0:
                return result.stdout or ""
            return f"Error reading file (Exit Code {result.exit_code}): {result.stderr or result.stdout}"
        except Exception as e:
            return f"System Error: {e}"

    def write_file(self, path: str, content: str) -> str:
        """Write content to a file."""
        # Human-in-the-loop validation
        if self.validation_required:
            answer = interrupt({
                "action": "write_file",
                "path": path,
                "content_preview": content[:200] + ("..." if len(content) > 200 else ""),
                "description": f"Write to file: {path}"
            })
            if answer != "approve":
                return "Action cancelled by user."

        try:
            orchestrator, session = self._get_orchestrator_and_session()
            # Use orchestrator's upload mechanism which is more robust
            result = orchestrator.upload(session, path, content.encode("utf-8"))
            if result.exit_code == 0:
                return f"Successfully wrote to {path}"
            return f"Error writing file (Exit Code {result.exit_code}): {result.stderr or result.stdout}"
        except Exception as e:
            return f"System Error: {e}"

    def list_files(self, path: str = ".") -> str:
        """List files in a directory."""
        return self.run_shell(f"ls -R {path}")

    def list_files_flat(self) -> List[str]:
        """Internal method to get a flat list of files without validation."""
        try:
            orchestrator, session = self._get_orchestrator_and_session()
            # List files recursively up to depth 3, excluding hidden files/dirs and common noise
            cmd = (
                "find . -maxdepth 3 "
                "-not -path '*/.*' "
                "-not -path '*/node_modules*' "
                "-not -path '*/__pycache__*' "
                "-not -path '*/venv*' "
                "-not -path '*/.venv*' "
                "-not -path '.' "
                "-type f"
            )
            result = orchestrator.execute(session, cmd)
            if result.exit_code == 0:
                # Clean up paths (remove leading ./)
                files = []
                for line in result.stdout.split("\n"):
                    line = line.strip()
                    if line.startswith("./"):
                        line = line[2:]
                    if line:
                        files.append(line)
                return sorted(files)
            return []
        except Exception as e:
            print(f"DEBUG: Error in list_files_flat: {e}")
            return []

    def ask_user(self, question: str, choices: Optional[List[str]] = None) -> str:
        """
        Ask the user a question when you need clarification or a decision. 
        Optionally provide a list of multiple-choice values for the user to pick from.
        The system will pause and wait for the user's response.
        """
        answer = interrupt({
            "action": "ask_user",
            "question": question,
            "choices": choices,
            "description": question
        })
        return str(answer)

    def browser_open_url(self, url: str) -> str:
        """
        Open a URL in a headless browser inside the sandbox and return the page title and a text preview.
        Use this when you need to research information, read documentation, or inspect a website.
        """
        script = f"""
python - << 'PY'
import sys
import json
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Error: 'playwright' package is not installed in the sandbox.")
    sys.exit(1)

url = {url!r}
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Use a persistent context if we want to support cookies/state? 
        # For now, just a simple new page.
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)
        title = page.title()
        text = page.inner_text("body")
        
        # Save state for subsequent actions? 
        # Persistent context would be better but requires more setup.
        
        browser.close()
        print(f"TITLE: {{title}}")
        print("CONTENT_START")
        print(text[:5000])
except Exception as e:
    print(f"Error: {{str(e)}}")
    sys.exit(1)
PY
"""
        try:
            orchestrator, session = self._get_orchestrator_and_session()
            result = orchestrator.execute(session, script, timeout_sec=60)
            if result.exit_code != 0:
                return f"Browser error: {result.stdout or result.stderr}"
            
            return result.stdout or "No output from browser."
        except Exception as e:
            return f"System error calling browser: {e}"

    def browser_click(self, url: str, selector: str) -> str:
        """
        Open a URL and click on an element identified by a CSS selector.
        Returns the page content after the click.
        """
        script = f"""
python - << 'PY'
import sys
from playwright.sync_api import sync_playwright

url = {url!r}
selector = {selector!r}
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        page.click(selector)
        page.wait_for_load_state("networkidle")
        text = page.inner_text("body")
        print("CONTENT_AFTER_CLICK")
        print(text[:5000])
        browser.close()
except Exception as e:
    print(f"Error: {{str(e)}}")
    sys.exit(1)
PY
"""
        try:
            orchestrator, session = self._get_orchestrator_and_session()
            result = orchestrator.execute(session, script, timeout_sec=60)
            return result.stdout or result.stderr
        except Exception as e:
            return str(e)

    def browser_type(self, url: str, selector: str, text: str, press_enter: bool = True) -> str:
        """
        Open a URL and type text into an element identified by a CSS selector.
        Returns the page content after typing.
        """
        script = f"""
python - << 'PY'
import sys
from playwright.sync_api import sync_playwright

url = {url!r}
selector = {selector!r}
text = {text!r}
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        page.type(selector, text)
        if {press_enter}:
            page.keyboard.press("Enter")
        page.wait_for_load_state("networkidle")
        content = page.inner_text("body")
        print("CONTENT_AFTER_TYPE")
        print(content[:5000])
        browser.close()
except Exception as e:
    print(f"Error: {{str(e)}}")
    sys.exit(1)
PY
"""
        try:
            orchestrator, session = self._get_orchestrator_and_session()
            result = orchestrator.execute(session, script, timeout_sec=60)
            return result.stdout or result.stderr
        except Exception as e:
            return str(e)

    def get_screenshot(self) -> str:
        """Take a screenshot of the current screen (if browser is active)."""
        return "Screenshot functionality is integrated with browser tools."

    def request_user_takeover(self, reason: str) -> str:
        """
        Request the user to take control of the browser or terminal. 
        Use this when you encounter a login, CAPTCHA, or complex interaction you cannot handle.
        """
        # Explicit wait for user intervention
        interrupt({
            "action": "user_takeover",
            "reason": reason,
            "description": f"User takeover requested: {reason}"
        })
        return f"User has resumed after takeover. Reason was: {reason}"

def get_tools(sandbox_session_id: str, validation_required: bool = True):
    ts = SandboxToolset(sandbox_session_id, validation_required=validation_required)
    return [
        tool(ts.run_shell),
        tool(ts.read_file),
        tool(ts.write_file),
        tool(ts.list_files),
        tool(ts.request_user_takeover),
        tavily_web_search
    ]