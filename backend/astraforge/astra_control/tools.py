import os
import json
import base64
import shlex
import subprocess
from typing import Optional, List, Dict, Any
from langchain_core.tools import tool

class SandboxToolset:
    def __init__(self, sandbox_session_id: str):
        # We assume the container name follows the convention "sandbox-{id}"
        self.container_name = f"sandbox-{sandbox_session_id}"
        self.user = os.getenv("SANDBOX_DOCKER_USER", "").strip()
        print(f"DEBUG: Initialized SandboxToolset for container {self.container_name} as user {self.user or 'default'}")

    def _exec(self, command: str, cwd: Optional[str] = None) -> Dict[str, Any]:
        print(f"DEBUG: Executing in container {self.container_name}: {command}")
        
        # Wrap command to handle CWD
        full_command = command
        if cwd:
            full_command = f"cd {shlex.quote(cwd)} && {command}"
        
        cmd = ["docker", "exec"]
        if self.user:
            cmd.extend(["--user", self.user])
        cmd.extend([self.container_name, "sh", "-c", full_command])
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = process.communicate()
            exit_code = process.returncode
            
            print(f"DEBUG: Executed command. Exit code: {exit_code}")
            if stdout:
                print(f"DEBUG: Stdout (first 100 chars): {stdout[:100].strip()}")
            if stderr:
                print(f"DEBUG: Stderr (first 100 chars): {stderr[:100].strip()}")
            
            return {
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr
            }
        except Exception as e:
            print(f"DEBUG: Docker exec failed: {e}")
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e)
            }

    def run_shell(self, command: str, cwd: Optional[str] = None) -> str:
        """Execute a shell command in the Ubuntu environment."""
        result = self._exec(command, cwd=cwd)
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        exit_code = result.get("exit_code", 0)
        return f"Exit Code: {exit_code}\nStdout: {stdout}\nStderr: {stderr}"

    def read_file(self, path: str) -> str:
        """Read the content of a file."""
        # Use cat via docker exec
        result = self._exec(f"cat {shlex.quote(path)}")
        if result["exit_code"] == 0:
            return result["stdout"]
        return f"Error: {result['stderr']}"

    def write_file(self, path: str, content: str) -> str:
        """Write content to a file."""
        # Use base64 to safely write content
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        cmd = f"echo '{encoded}' | base64 -d > {shlex.quote(path)}"
        result = self._exec(cmd)
        if result["exit_code"] == 0:
            return f"Successfully wrote to {path}"
        return f"Error: {result['stderr']}"

    def list_files(self, path: str = ".") -> str:
        """List files in a directory."""
        return self.run_shell(f"ls -R {path}")

    def get_screenshot(self) -> str:
        """Take a screenshot of the current screen (if browser is active)."""
        return "Screenshot functionality is integrated with browser tools."

    def request_user_takeover(self, reason: str) -> str:
        """
        Request the user to take control of the browser or terminal. 
        Use this when you encounter a login, CAPTCHA, or complex interaction you cannot handle.
        """
        return f"TAKEOVER_REQUESTED: {reason}"

def get_tools(sandbox_session_id: str):
    ts = SandboxToolset(sandbox_session_id)
    return [
        tool(ts.run_shell),
        tool(ts.read_file),
        tool(ts.write_file),
        tool(ts.list_files),
        tool(ts.request_user_takeover)
    ]
