"""In-memory repository useful for development and unit tests."""

from __future__ import annotations

from typing import Dict

from astraforge.application.use_cases import RequestRepository
from astraforge.domain.models.request import Request


class InMemoryRequestRepository(RequestRepository):
    def __init__(self) -> None:
        self._store: Dict[str, Request] = {}

    def save(self, request: Request) -> None:
        self._store[request.id] = request

    def get(self, request_id: str) -> Request:
        return self._store[request_id]

    def list(self) -> list[Request]:
        return list(self._store.values())
