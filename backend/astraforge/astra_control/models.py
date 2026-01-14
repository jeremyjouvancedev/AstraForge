from django.conf import settings
from django.db import models
from django.utils import timezone
import uuid

class AstraControlSession(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", "Created"
        RUNNING = "running", "Running"
        PAUSED = "paused", "Paused"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="astra_control_sessions"
    )
    name = models.CharField(max_length=255, blank=True)
    goal = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CREATED)
    sandbox_session = models.ForeignKey(
        "sandbox.SandboxSession", on_delete=models.SET_NULL, null=True, blank=True
    )
    last_snapshot_id = models.UUIDField(null=True, blank=True)
    state = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name or self.goal[:50]} ({self.status})"
