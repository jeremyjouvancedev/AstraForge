from __future__ import annotations

import dataclasses
import json
from typing import Any

from langchain_core.messages import BaseMessage, BaseMessageChunk, message_to_dict
from pydantic import BaseModel


def jsonable_chunk(obj: Any) -> Any:
    """Recursively convert LangGraph / LangChain objects to JSON-friendly types."""
    if isinstance(obj, (BaseMessage, BaseMessageChunk)):
        return message_to_dict(obj)
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    if isinstance(obj, dict):
        return {k: jsonable_chunk(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable_chunk(v) for v in obj]
    return obj


def encode_sse(payload: dict, event: str | None = None) -> str:
    """Turn a JSON-serializable payload into an SSE frame."""
    data = json.dumps(payload, ensure_ascii=False)
    lines: list[str] = []
    if event:
        lines.append(f"event: {event}")
    lines.append(f"data: {data}")
    return "\n".join(lines) + "\n\n"

