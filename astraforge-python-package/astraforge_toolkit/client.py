from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Iterator, List, Mapping, MutableMapping, Optional

import requests
from requests import Response, Session


class DeepAgentError(RuntimeError):
    """Base error for DeepAgent client failures."""


@dataclass
class DeepAgentConversation:
    """Lightweight wrapper around a DeepAgent conversation payload."""

    conversation_id: str
    sandbox_session_id: str
    status: str
    raw: Mapping[str, Any]


@dataclass
class SandboxSession:
    """Sandbox session metadata returned by the sandbox API."""

    session_id: str
    workspace_path: str
    status: str | None = None
    image: str | None = None
    mode: str | None = None
    idle_timeout_sec: int | None = None
    max_lifetime_sec: int | None = None
    created_at: str | None = None
    updated_at: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class SandboxArtifact:
    """Artifact metadata returned by sandbox file export endpoints."""

    artifact_id: str
    filename: str
    content_type: str | None
    size_bytes: int
    download_url: str | None
    raw: Mapping[str, Any] = field(default_factory=dict)


class DeepAgentClient:
    """Synchronous client for the AstraForge DeepAgent HTTP API.

    This client talks to the same `/api/deepagent/...` and `/api/sandbox/...` endpoints
    that the AstraForge UI uses. It is intentionally small and dependency-light so that
    other applications can reuse the hosted DeepAgent + sandbox backend without pulling
    in Django or Celery.

    Example:
        >>> from astraforge_toolkit import DeepAgentClient
        >>> client = DeepAgentClient(
        ...     base_url="https://astra.example.com/api",
        ...     api_key="your-api-key",
        ... )
        >>> conv = client.create_conversation()
        >>> for chunk in client.stream_message(conv.conversation_id, "Hello, sandbox!"):
        ...     print(chunk.get("tokens") or chunk.get("messages"))
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float | None = 60.0,
        session: Session | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required")
        if not api_key:
            raise ValueError("api_key is required")

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._session: Session = session or requests.Session()
        self._session.headers.setdefault("X-Api-Key", self.api_key)

    # Public API ------------------------------------------------------------

    def create_conversation(
        self,
        session_params: Optional[Mapping[str, Any]] = None,
    ) -> DeepAgentConversation:
        url = f"{self.base_url}/deepagent/conversations/"
        payload: Dict[str, Any] = dict(session_params or {})
        response = self._session.post(url, json=payload, timeout=self.timeout)
        data = self._parse_json(response, expected_status=201)
        try:
            conversation_id = str(data["conversation_id"])
            sandbox_session_id = str(data["sandbox_session_id"])
            status = str(data.get("status", ""))
        except Exception as exc:  # noqa: BLE001
            raise DeepAgentError(f"Unexpected conversation payload: {data}") from exc
        return DeepAgentConversation(
            conversation_id=conversation_id,
            sandbox_session_id=sandbox_session_id,
            status=status,
            raw=data,
        )

    def create_sandbox_session(
        self,
        session_params: Optional[Mapping[str, Any]] = None,
    ) -> SandboxSession:
        """Create a sandbox session without creating a DeepAgent conversation."""
        url = f"{self.base_url}/sandbox/sessions/"
        payload: Dict[str, Any] = dict(session_params or {})
        response = self._session.post(url, json=payload, timeout=self.timeout)
        data = self._parse_json(response, expected_status=201)
        return self._build_sandbox_session(data)

    def list_sandbox_sessions(self) -> List[SandboxSession]:
        """List sandbox sessions for the authenticated user."""
        url = f"{self.base_url}/sandbox/sessions/"
        response = self._session.get(url, timeout=self.timeout)
        data = self._parse_json(response, expected_status=200)
        sessions_payload: Any = data
        if isinstance(data, Mapping) and "results" in data:
            sessions_payload = data.get("results")
        if not isinstance(sessions_payload, list):
            raise DeepAgentError(f"Unexpected sandbox sessions payload: {data}")
        return [self._build_sandbox_session(item) for item in sessions_payload]

    def get_sandbox_session(self, session_id: str) -> SandboxSession:
        if not session_id:
            raise ValueError("session_id is required")

        url = f"{self.base_url}/sandbox/sessions/{session_id}/"
        response = self._session.get(url, timeout=self.timeout)
        data = self._parse_json(response, expected_status=200)
        return self._build_sandbox_session(data)

    def delete_sandbox_session(self, session_id: str) -> None:
        if not session_id:
            raise ValueError("session_id is required")

        url = f"{self.base_url}/sandbox/sessions/{session_id}/"
        response = self._session.delete(url, timeout=self.timeout)
        self._ensure_ok(response, expected_status=204)

    def stop_sandbox_session(self, session_id: str) -> None:
        if not session_id:
            raise ValueError("session_id is required")

        url = f"{self.base_url}/sandbox/sessions/{session_id}/stop/"
        response = self._session.post(url, timeout=self.timeout)
        self._ensure_ok(response, expected_status=204)

    def heartbeat_sandbox_session(self, session_id: str) -> Mapping[str, Any]:
        if not session_id:
            raise ValueError("session_id is required")

        url = f"{self.base_url}/sandbox/sessions/{session_id}/heartbeat/"
        response = self._session.post(url, timeout=self.timeout)
        return self._parse_json(response, expected_status=200)

    def send_message(
        self,
        conversation_id: str,
        messages: Iterable[Mapping[str, Any]],
        *,
        stream: bool = False,
    ) -> Mapping[str, Any] | Iterator[Mapping[str, Any]]:
        if not conversation_id:
            raise ValueError("conversation_id is required")

        url = f"{self.base_url}/deepagent/conversations/{conversation_id}/messages/"
        body = {
            "messages": list(messages),
            "stream": stream,
        }
        if not stream:
            response = self._session.post(url, json=body, timeout=self.timeout)
            return self._parse_json(response, expected_status=200)

        response = self._session.post(
            url,
            json=body,
            timeout=self.timeout,
            stream=True,
            headers={"Accept": "text/event-stream", **self._session.headers},
        )
        self._ensure_ok(response, expected_status=200)
        return self._iter_sse(response)

    def stream_message(
        self,
        conversation_id: str,
        content: str,
    ) -> Iterator[Mapping[str, Any]]:
        message = {"role": "user", "content": content}
        iterator = self.send_message(
            conversation_id=conversation_id,
            messages=[message],
            stream=True,
        )
        assert isinstance(iterator, Iterator)
        return iterator

    def upload_file(
        self,
        session_id: str,
        path: str,
        *,
        content: bytes | str,
        encoding: str = "utf-8",
    ) -> Mapping[str, Any]:
        """Upload raw bytes into a sandbox session at the given path."""
        if not session_id:
            raise ValueError("session_id is required")
        if not path:
            raise ValueError("path is required")

        body: bytes
        if isinstance(content, str):
            body = content.encode(encoding)
        else:
            body = content

        url = f"{self.base_url}/sandbox/sessions/{session_id}/files/upload"
        response = self._session.post(
            url,
            params={"path": path},
            data=body,
            timeout=self.timeout,
            headers={"Content-Type": "application/octet-stream"},
        )
        return self._parse_json(response, expected_status=200)

    def get_file_content(
        self,
        session_id: str,
        path: str,
        *,
        encoding: str | None = None,
    ) -> bytes | str:
        """Fetch file bytes from a sandbox session. Optionally decode to text."""
        if not session_id:
            raise ValueError("session_id is required")
        if not path:
            raise ValueError("path is required")

        url = f"{self.base_url}/sandbox/sessions/{session_id}/files/content"
        response = self._session.get(
            url,
            params={"path": path},
            timeout=self.timeout,
        )
        self._ensure_ok(response, expected_status=200)
        if encoding:
            return response.content.decode(encoding)
        return response.content

    def export_file(
        self,
        session_id: str,
        path: str,
        *,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> SandboxArtifact:
        """Export a file from the sandbox and receive an artifact descriptor."""
        if not session_id:
            raise ValueError("session_id is required")
        if not path:
            raise ValueError("path is required")

        url = f"{self.base_url}/sandbox/sessions/{session_id}/files/export/"
        body: Dict[str, Any] = {"path": path}
        if filename:
            body["filename"] = filename
        if content_type:
            body["content_type"] = content_type
        response = self._session.post(url, json=body, timeout=self.timeout)
        data = self._parse_json(response, expected_status=201)
        return self._build_artifact(data)

    # Internal helpers ------------------------------------------------------

    def _parse_json(self, response: Response, *, expected_status: int) -> MutableMapping[str, Any]:
        self._ensure_ok(response, expected_status=expected_status)
        try:
            return response.json()  # type: ignore[return-value]
        except json.JSONDecodeError as exc:  # pragma: no cover - network edge case
            raise DeepAgentError(f"Invalid JSON response from {response.url}") from exc

    def _ensure_ok(self, response: Response, *, expected_status: int) -> None:
        if response.status_code == expected_status:
            return
        detail: Any
        try:
            payload = response.json()
            detail = payload.get("detail") or payload
        except Exception:  # pragma: no cover - fallback path
            detail = response.text
        raise DeepAgentError(
            f"Request to {response.url} failed with status {response.status_code}: {detail!r}"
        )

    def _iter_sse(self, response: Response) -> Iterator[Mapping[str, Any]]:
        try:
            for raw_line in response.iter_lines(decode_unicode=True):
                if raw_line is None:
                    continue
                line = raw_line.strip()
                if not line or not line.startswith("data:"):
                    continue

                json_payload = line[len("data:") :].strip()
                if not json_payload:
                    continue
                try:
                    parsed = json.loads(json_payload)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    yield parsed
                else:
                    yield {"data": parsed}
        finally:
            response.close()

    def _build_sandbox_session(self, data: Mapping[str, Any]) -> SandboxSession:
        try:
            session_id = str(data["id"])
        except Exception as exc:  # noqa: BLE001
            raise DeepAgentError(f"Unexpected sandbox session payload: {data}") from exc
        workspace_path = str(data.get("workspace_path") or "")
        status = str(data.get("status")) if data.get("status") is not None else None
        image = str(data.get("image")) if data.get("image") is not None else None
        mode = str(data.get("mode")) if data.get("mode") is not None else None
        idle_timeout = data.get("idle_timeout_sec")
        max_lifetime = data.get("max_lifetime_sec")
        created_at = str(data.get("created_at")) if data.get("created_at") else None
        updated_at = str(data.get("updated_at")) if data.get("updated_at") else None
        return SandboxSession(
            session_id=session_id,
            workspace_path=workspace_path,
            status=status,
            image=image,
            mode=mode,
            idle_timeout_sec=int(idle_timeout) if idle_timeout is not None else None,
            max_lifetime_sec=int(max_lifetime) if max_lifetime is not None else None,
            created_at=created_at,
            updated_at=updated_at,
            raw=data,
        )

    def _build_artifact(self, data: Mapping[str, Any]) -> SandboxArtifact:
        try:
            artifact_id = str(data["id"])
            filename = str(data.get("filename") or "")
        except Exception as exc:  # noqa: BLE001
            raise DeepAgentError(f"Unexpected sandbox artifact payload: {data}") from exc
        content_type = str(data.get("content_type")) if data.get("content_type") else None
        try:
            size_bytes = int(data.get("size_bytes") or 0)
        except (TypeError, ValueError):
            size_bytes = 0
        download_url = str(data.get("download_url")) if data.get("download_url") else None
        return SandboxArtifact(
            artifact_id=artifact_id,
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            download_url=download_url,
            raw=data,
        )
