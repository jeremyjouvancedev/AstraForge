"""In-memory run log streamer used for local development and unit tests."""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from typing import Dict, Iterable

from astraforge.domain.providers.interfaces import RunLogStreamer


@dataclass
class InMemoryRunLogStreamer(RunLogStreamer):
    """Thread-safe pub/sub channel emitting events per request id."""

    maxsize: int = 0
    _channels: Dict[str, "queue.Queue[dict[str, object]]"] = field(
        default_factory=dict, init=False
    )
    _locks: Dict[str, threading.Lock] = field(default_factory=dict, init=False)

    def publish(self, request_id: str, event: dict[str, object]) -> None:
        channel = self._get_channel(request_id)
        channel.put(event)

    def stream(self, request_id: str) -> Iterable[dict[str, object]]:
        channel = self._get_channel(request_id)
        while True:
            event = channel.get()
            yield event
            if event.get("type") == "completed":
                break

    def _get_channel(self, request_id: str) -> "queue.Queue[dict[str, object]]":
        if request_id not in self._channels:
            self._locks.setdefault(request_id, threading.Lock())
            with self._locks[request_id]:
                if request_id not in self._channels:
                    self._channels[request_id] = queue.Queue(maxsize=self.maxsize)
        return self._channels[request_id]


def from_env() -> InMemoryRunLogStreamer:
    return InMemoryRunLogStreamer()
