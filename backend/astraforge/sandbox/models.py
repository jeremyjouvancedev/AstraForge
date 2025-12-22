from __future__ import annotations

import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from astraforge.accounts.models import Workspace


class SandboxSession(models.Model):
    class Mode(models.TextChoices):
        DOCKER = "docker", "Docker"
        KUBERNETES = "k8s", "Kubernetes"

    class Status(models.TextChoices):
        STARTING = "starting", "Starting"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"
        TERMINATED = "terminated", "Terminated"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sandbox_sessions",
    )
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="workspace_sessions",
        null=True,
        blank=True,
    )
    mode = models.CharField(max_length=12, choices=Mode.choices)
    image = models.CharField(max_length=255)
    cpu = models.CharField(max_length=32, blank=True)
    memory = models.CharField(max_length=32, blank=True)
    ephemeral_storage = models.CharField(max_length=32, blank=True)
    restore_snapshot_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.STARTING)
    ref = models.CharField(
        max_length=128,
        blank=True,
        help_text="Runtime reference (docker:// or k8s:// namespace/pod)",
    )
    control_endpoint = models.CharField(
        max_length=255,
        blank=True,
        help_text="Where the sandbox daemon is reachable (exec or HTTP)",
    )
    workspace_path = models.CharField(max_length=255, default="/workspace")
    idle_timeout_sec = models.PositiveIntegerField(default=300)
    max_lifetime_sec = models.PositiveIntegerField(default=3600)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    artifact_base_url = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    cpu_seconds = models.FloatField(default=0)
    storage_bytes = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["mode"]),
        ]

    def save(self, *args, **kwargs):  # pragma: no cover - trivial
        if self.max_lifetime_sec and not self.expires_at:
            self.expires_at = timezone.now() + timedelta(seconds=self.max_lifetime_sec)
        super().save(*args, **kwargs)

    def mark_heartbeat(self):
        self.last_heartbeat_at = timezone.now()
        self.last_activity_at = self.last_activity_at or self.last_heartbeat_at
        self.save(update_fields=["last_heartbeat_at", "last_activity_at", "updated_at"])

    def mark_activity(self):
        now = timezone.now()
        self.last_activity_at = now
        self.last_heartbeat_at = now
        self.save(update_fields=["last_activity_at", "last_heartbeat_at", "updated_at"])

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return f"SandboxSession(id={self.id}, mode={self.mode}, status={self.status})"


class SandboxSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        SandboxSession, on_delete=models.CASCADE, related_name="snapshots"
    )
    label = models.CharField(max_length=255, blank=True)
    s3_key = models.CharField(max_length=512, blank=True)
    archive_path = models.CharField(max_length=512, blank=True)
    size_bytes = models.BigIntegerField(default=0)
    include_paths = models.JSONField(default=list, blank=True)
    exclude_paths = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["session"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return f"SandboxSnapshot(id={self.id}, session={self.session_id})"


class SandboxArtifact(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        SandboxSession, on_delete=models.CASCADE, related_name="artifacts"
    )
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True)
    size_bytes = models.BigIntegerField(default=0)
    storage_path = models.CharField(
        max_length=512, help_text="Path inside sandbox or remote storage key"
    )
    download_url = models.CharField(max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["session"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return f"SandboxArtifact(id={self.id}, session={self.session_id}, filename={self.filename})"
