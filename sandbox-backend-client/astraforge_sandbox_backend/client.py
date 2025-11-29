from __future__ import annotations

import json
from dataclasses import dataclass
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


class DeepAgentClient:
    """Synchronous client for the AstraForge DeepAgent HTTP API.

    This client talks to the same `/api/deepagent/...` and `/api/sandbox/...` endpoints
    that the AstraForge UI uses. It is intentionally small and dependency-light so that
    other applications can reuse the hosted DeepAgent + sandbox backend without pulling
    in Django or Celery.

    Example:
        >>> from astraforge_sandbox_backend import DeepAgentClient
        >>> client = DeepAgentClient(
        ...     base_url=\"https://astra.example.com/api\",
        ...     api_key=\"your-api-key\",
        ... )
        >>> conv = client.create_conversation()
        >>> for chunk in client.stream_message(conv.conversation_id, \"Hello, sandbox!\"):
        ...     print(chunk.get(\"tokens\") or chunk.get(\"messages\"))
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float | None = 60.0,
        session: Session | None = None,
    ) -> None:
        """
        Args:
            base_url: Base API URL, typically \"https://host/api\" or \"http://localhost:8000/api\".
            api_key: AstraForge API key (sent as X-Api-Key).
            timeout: Default request timeout in seconds (None to disable).
            session: Optional preconfigured `requests.Session`.
        """
        if not base_url:
            raise ValueError("base_url is required")
        if not api_key:
            raise ValueError("api_key is required")

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._session: Session = session or requests.Session()
        # Let callers override headers on the provided session if they want to.
        self._session.headers.setdefault("X-Api-Key", self.api_key)

    # Public API ------------------------------------------------------------

    def create_conversation(
        self,
        session_params: Optional[Mapping[str, Any]] = None,
    ) -> DeepAgentConversation:
        """Create a new DeepAgent conversation + sandbox session.

        `session_params` are forwarded directly to the sandbox session serializer.
        Useful keys include:
            - mode: \"docker\" | \"k8s\"
            - image: sandbox image name
            - cpu / memory / ephemeral_storage
            - idle_timeout_sec / max_lifetime_sec
        """
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

    def send_message(
        self,
        conversation_id: str,
        messages: Iterable[Mapping[str, Any]],
        *,
        stream: bool = False,
    ) -> Mapping[str, Any] | Iterator[Mapping[str, Any]]:
        """Send a message to DeepAgent.

        When `stream=False` (default), the server computes the full reply before
        responding and this method returns the final JSON payload.

        When `stream=True`, this method returns an iterator yielding JSON payloads
        decoded from the server-sent events stream.
        """
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
        """Convenience wrapper around `send_message` for a single user message."""
        message = {"role": "user", "content": content}
        iterator = self.send_message(
            conversation_id=conversation_id,
            messages=[message],
            stream=True,
        )
        assert isinstance(iterator, Iterator)
        return iterator

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
        """Yield JSON payloads from a text/event-stream response."""
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
                    # Ignore malformed frames to keep the stream resilient.
                    continue
                if isinstance(parsed, dict):
                    # Most deep agent chunks are dict-like; yield as-is.
                    yield parsed
                else:
                    # Wrap non-dict payloads for consistency.
                    yield {"data": parsed}
        finally:
            response.close()

