"""Redis Streams-backed run log streamer."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Iterable

import redis

from astraforge.domain.providers.interfaces import RunLogStreamer

logger = logging.getLogger(__name__)


@dataclass
class RedisRunLogStreamer(RunLogStreamer):
    """Clear-text event streamer backed by Redis Streams."""

    client: "redis.Redis[str]"
    stream_prefix: str = "runlog"
    stream_maxlen: int = 512
    block_ms: int = 5_000
    retention_seconds: int = 6 * 60 * 60  # 6 hours

    def publish(self, request_id: str, event: dict[str, object]) -> None:
        payload = json.dumps(event)
        stream_key = self._stream_key(request_id)
        try:
            self.client.xadd(
                stream_key,
                {"data": payload},
                maxlen=self.stream_maxlen,
                approximate=True,
            )
            if self.retention_seconds:
                self.client.expire(stream_key, self.retention_seconds)
        except Exception:  # pragma: no cover - network errors
            logger.exception("Failed to publish run log entry", extra={"request_id": request_id})

    def stream(self, request_id: str) -> Iterable[dict[str, object]]:
        stream_key = self._stream_key(request_id)
        last_id = "0-0"
        while True:
            try:
                response = self.client.xread({stream_key: last_id}, block=self.block_ms, count=10)
            except Exception:  # pragma: no cover - network errors
                logger.exception(
                    "Failed to read run log stream", extra={"request_id": request_id}
                )
                continue

            if not response:
                continue

            for _, events in response:
                for entry_id, fields in events:
                    payload = fields.get("data")
                    if payload is None:
                        logger.warning(
                            "Skipping malformed run log entry", extra={"request_id": request_id}
                        )
                        last_id = entry_id
                        continue

                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        logger.warning(
                            "Skipping undecodable run log entry", extra={"request_id": request_id}
                        )
                        last_id = entry_id
                        continue

                    yield event
                    last_id = entry_id

                    if event.get("type") == "completed":
                        return

    def _stream_key(self, request_id: str) -> str:
        return f"{self.stream_prefix}:{request_id}"


def from_env() -> RedisRunLogStreamer:
    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    client: "redis.Redis[str]" = redis.from_url(url, decode_responses=True)
    stream_prefix = os.environ.get("RUN_LOG_STREAM_PREFIX", "runlog")
    try:
        maxlen = int(os.environ.get("RUN_LOG_STREAM_MAXLEN", "512"))
    except ValueError:
        maxlen = 512
    try:
        block_ms = int(os.environ.get("RUN_LOG_STREAM_BLOCK_MS", "5000"))
    except ValueError:
        block_ms = 5_000
    try:
        retention = int(os.environ.get("RUN_LOG_RETENTION_SECONDS", str(6 * 60 * 60)))
    except ValueError:
        retention = 6 * 60 * 60
    return RedisRunLogStreamer(
        client=client,
        stream_prefix=stream_prefix,
        stream_maxlen=maxlen,
        block_ms=block_ms,
        retention_seconds=retention,
    )
