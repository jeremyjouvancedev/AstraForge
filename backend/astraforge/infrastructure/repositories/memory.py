"""In-memory repository useful for development and unit tests."""

from __future__ import annotations

from typing import Dict

from astraforge.application.use_cases import RequestRepository
from astraforge.domain.models.request import Request


class InMemoryRequestRepository(RequestRepository):
    def __init__(self) -> None:
        self._store: Dict[str, Request] = {}

    def save(self, request: Request) -> None:
        existing = self._store.get(request.id)
        if existing and existing.user_id and request.user_id and existing.user_id != request.user_id:
            raise PermissionError("Request already exists for a different user.")
        self._store[request.id] = request

    def get(self, request_id: str, *, user_id: str | None = None) -> Request:
        request = self._store[request_id]
        if user_id is not None and request.user_id != user_id:
            raise KeyError(request_id)
        return request

    def list(self, *, user_id: str | None = None) -> list[Request]:
        if user_id is None:
            return list(self._store.values())
        return [req for req in self._store.values() if req.user_id == user_id]
