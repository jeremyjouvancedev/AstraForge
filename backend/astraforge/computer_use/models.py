from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from astraforge.accounts.models import Workspace
from astraforge.sandbox.models import SandboxSession


class ComputerUseRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        AWAITING_ACK = "awaiting_ack", "Awaiting approval"
        COMPLETED = "completed", "Completed"
        BLOCKED_POLICY = "blocked_policy", "Blocked by policy"
        DENIED_APPROVAL = "denied_approval", "Denied approval"
        TIMED_OUT = "timed_out", "Timed out"
        MAX_STEPS = "max_steps", "Max steps"
        EXECUTION_ERROR = "execution_error", "Execution error"
        USER_CANCEL = "user_cancel", "User canceled"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="computer_use_runs",
    )
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.SET_NULL,
        related_name="computer_use_runs",
        null=True,
        blank=True,
    )
    sandbox_session = models.ForeignKey(
        SandboxSession,
        on_delete=models.SET_NULL,
        related_name="computer_use_runs",
        null=True,
        blank=True,
    )
    goal = models.TextField()
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.RUNNING)
    stop_reason = models.CharField(max_length=64, blank=True)
    config = models.JSONField(default=dict, blank=True)
    state = models.JSONField(default=dict, blank=True)
    trace_dir = models.CharField(max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return f"ComputerUseRun(id={self.id}, status={self.status})"
