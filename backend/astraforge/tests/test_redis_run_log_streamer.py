from __future__ import annotations

import pytest

import fakeredis

from astraforge.infrastructure.event_bus.redis_streams import RedisRunLogStreamer


def _make_streamer(**kwargs) -> RedisRunLogStreamer:
    client = fakeredis.FakeRedis(decode_responses=True)
    return RedisRunLogStreamer(client=client, **kwargs)


def test_streamer_replays_existing_events() -> None:
    streamer = _make_streamer(block_ms=10)
    streamer.publish("req-1", {"type": "message", "message": "hello"})
    streamer.publish("req-1", {"type": "completed"})

    iterator = streamer.stream("req-1")
    first = next(iterator)
    second = next(iterator)

    assert first["message"] == "hello"
    assert second["type"] == "completed"
    with pytest.raises(StopIteration):
        next(iterator)


def test_streamer_handles_events_written_after_subscription() -> None:
    streamer = _make_streamer(block_ms=10)
    iterator = streamer.stream("req-2")

    streamer.publish("req-2", {"type": "progress", "step": 1})
    streamer.publish("req-2", {"type": "completed"})

    events = list(iterator)
    assert events == [
        {"type": "progress", "step": 1},
        {"type": "completed"},
    ]
