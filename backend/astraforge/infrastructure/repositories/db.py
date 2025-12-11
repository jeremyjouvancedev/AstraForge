from __future__ import annotations

from dataclasses import asdict
from typing import Dict, List

from django.apps import apps

from astraforge.application.use_cases import RequestRepository
from astraforge.domain.models.request import Attachment, Request, RequestPayload, RequestState


class DjangoRequestRepository(RequestRepository):
    """Django ORM backed request repository."""

    def __init__(self) -> None:
        self.model = apps.get_model("requests", "RequestRecord")

    def save(self, request: Request) -> None:
        payload = self._serialize_payload(request.payload)
        existing = self.model.objects.filter(id=request.id).first()
        if (
            existing
            and existing.user_id
            and request.user_id
            and str(existing.user_id) != str(request.user_id)
        ):
            raise PermissionError("Request already exists for a different user.")
        defaults: Dict[str, object] = {
            "user_id": request.user_id or None,
            "tenant_id": request.tenant_id,
            "source": request.source,
            "sender": request.sender,
            "payload": payload,
            "state": request.state.value,
            "artifacts": request.artifacts,
            "metadata": request.metadata,
        }
        record, _created = self.model.objects.update_or_create(
            id=request.id,
            defaults=defaults,
        )
        # ensure timestamps are in sync with domain entity
        request.created_at = record.created_at
        request.updated_at = record.updated_at

    def get(self, request_id: str, *, user_id: str | None = None) -> Request:
        try:
            query = self.model.objects
            if user_id is not None:
                query = query.filter(user_id=user_id)
            record = query.get(id=request_id)
        except self.model.DoesNotExist as exc:
            raise KeyError(request_id) from exc
        return self._to_domain(record)

    def list(self, *, user_id: str | None = None) -> List[Request]:
        query = self.model.objects
        if user_id is not None:
            query = query.filter(user_id=user_id)
        return [self._to_domain(record) for record in query.order_by("-created_at")]

    # helpers -----------------------------------------------------------

    def _serialize_payload(self, payload: RequestPayload) -> Dict[str, object]:
        return {
            "title": payload.title,
            "description": payload.description,
            "context": payload.context,
            "attachments": [asdict(att) for att in payload.attachments],
        }

    def _deserialize_payload(self, payload: Dict[str, object]) -> RequestPayload:
        attachments = [
            Attachment(**attachment)
            for attachment in payload.get("attachments", [])  # type: ignore[arg-type]
        ]
        return RequestPayload(
            title=payload.get("title", ""),
            description=payload.get("description", ""),
            context=payload.get("context", {}),
            attachments=attachments,
        )

    def _to_domain(self, record) -> Request:
        payload = self._deserialize_payload(record.payload)
        request = Request(
            id=str(record.id),
            user_id=str(record.user_id) if record.user_id else "",
            tenant_id=record.tenant_id,
            source=record.source,
            sender=record.sender,
            payload=payload,
            state=RequestState(record.state),
            created_at=record.created_at,
            updated_at=record.updated_at,
            artifacts=record.artifacts or {},
            metadata=record.metadata or {},
        )
        return request
