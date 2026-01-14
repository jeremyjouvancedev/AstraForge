from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class RequestRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="requests",
        null=True,
        blank=True,
    )
    tenant_id = models.CharField(max_length=100)
    source = models.CharField(max_length=100)
    sender = models.EmailField(blank=True)
    payload = models.JSONField()
    state = models.CharField(max_length=32)
    artifacts = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "astraforge_requests"
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover - debugging helper
        return f"RequestRecord(id={self.id}, state={self.state})"
