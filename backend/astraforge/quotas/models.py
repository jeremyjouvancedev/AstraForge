from __future__ import annotations

import uuid
from datetime import date

from django.db import models
from django.utils import timezone

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - type hints only
    from astraforge.accounts.models import Workspace


def _month_start(value: date | None = None) -> date:
    reference = value or timezone.now().date()
    return reference.replace(day=1)


class WorkspaceQuotaLedger(models.Model):
    """Monthly aggregate of workspace resource consumption."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "accounts.Workspace",
        on_delete=models.CASCADE,
        related_name="quota_ledgers",
    )
    period_start = models.DateField(default=_month_start)
    request_count = models.PositiveIntegerField(default=0)
    sandbox_sessions = models.PositiveIntegerField(default=0)
    sandbox_seconds = models.PositiveIntegerField(default=0)
    artifacts_bytes = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-period_start", "-updated_at"]
        unique_together = ("workspace", "period_start")

    def __str__(self) -> str:  # pragma: no cover - debugging helper
        return f"WorkspaceQuotaLedger(workspace={self.workspace_id}, period_start={self.period_start})"

    @classmethod
    def period_for(cls, reference: date | None = None) -> date:
        return _month_start(reference)

    @classmethod
    def for_workspace(
        cls,
        workspace: "Workspace",
        *,
        reference: date | None = None,
        lock: bool = False,
    ) -> "WorkspaceQuotaLedger":
        period_start = cls.period_for(reference)
        query = cls.objects
        if lock:
            query = query.select_for_update()
        ledger, _ = query.get_or_create(
            workspace=workspace,
            period_start=period_start,
        )
        return ledger
