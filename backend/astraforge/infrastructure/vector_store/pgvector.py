"""pgvector-backed VectorStore implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from astraforge.domain.providers.interfaces import VectorStore


@dataclass
class PgVectorStore(VectorStore):
    connection: object  # pragma: no cover - placeholder

    def upsert(self, namespace: str, items: Iterable[dict]) -> None:  # pragma: no cover
        raise NotImplementedError

    def query(self, namespace: str, query: str, top_k: int = 5):  # pragma: no cover
        raise NotImplementedError


def from_env() -> PgVectorStore:
    connection = object()  # placeholder handle
    return PgVectorStore(connection=connection)
