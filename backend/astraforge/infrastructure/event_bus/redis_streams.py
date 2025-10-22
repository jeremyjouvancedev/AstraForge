"""Redis Streams event bus implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class RedisStreamsBus:
    client: object  # pragma: no cover - placeholder

    def publish(self, channel: str, payload: dict) -> None:  # pragma: no cover
        raise NotImplementedError

    def subscribe(
        self, channel: str, handler: Callable[[dict], None]
    ) -> None:  # pragma: no cover
        raise NotImplementedError


def from_env() -> RedisStreamsBus:
    client = object()  # placeholder to avoid hard dependency
    return RedisStreamsBus(client=client)
