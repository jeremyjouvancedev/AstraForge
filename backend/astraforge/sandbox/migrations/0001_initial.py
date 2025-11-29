from __future__ import annotations

import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SandboxSession",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("mode", models.CharField(max_length=12, choices=[("docker", "Docker"), ("k8s", "Kubernetes")])),
                ("image", models.CharField(max_length=255)),
                ("cpu", models.CharField(max_length=32, blank=True)),
                ("memory", models.CharField(max_length=32, blank=True)),
                ("ephemeral_storage", models.CharField(max_length=32, blank=True)),
                ("restore_snapshot_id", models.UUIDField(null=True, blank=True)),
                (
                    "status",
                    models.CharField(
                        max_length=24,
                        choices=[
                            ("starting", "Starting"),
                            ("ready", "Ready"),
                            ("failed", "Failed"),
                            ("terminated", "Terminated"),
                        ],
                        default="starting",
                    ),
                ),
                (
                    "ref",
                    models.CharField(
                        max_length=128,
                        blank=True,
                        help_text="Runtime reference (docker:// or k8s:// namespace/pod)",
                    ),
                ),
                (
                    "control_endpoint",
                    models.CharField(
                        max_length=255,
                        blank=True,
                        help_text="Where the sandbox daemon is reachable (exec or HTTP)",
                    ),
                ),
                ("workspace_path", models.CharField(max_length=255, default="/workspace")),
                ("idle_timeout_sec", models.PositiveIntegerField(default=900)),
                ("max_lifetime_sec", models.PositiveIntegerField(default=3600)),
                ("last_heartbeat_at", models.DateTimeField(null=True, blank=True)),
                ("last_activity_at", models.DateTimeField(null=True, blank=True)),
                ("expires_at", models.DateTimeField(null=True, blank=True)),
                ("artifact_base_url", models.CharField(max_length=255, blank=True)),
                ("error_message", models.TextField(blank=True)),
                ("metadata", models.JSONField(default=dict, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sandbox_sessions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="SandboxSnapshot",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("label", models.CharField(max_length=255, blank=True)),
                ("s3_key", models.CharField(max_length=512, blank=True)),
                ("archive_path", models.CharField(max_length=512, blank=True)),
                ("size_bytes", models.BigIntegerField(default=0)),
                ("include_paths", models.JSONField(default=list, blank=True)),
                ("exclude_paths", models.JSONField(default=list, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="snapshots",
                        to="sandbox.sandboxsession",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="SandboxArtifact",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("filename", models.CharField(max_length=255)),
                ("content_type", models.CharField(max_length=100, blank=True)),
                ("size_bytes", models.BigIntegerField(default=0)),
                ("storage_path", models.CharField(max_length=512, help_text="Path inside sandbox or remote storage key")),
                ("download_url", models.CharField(max_length=512, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="artifacts",
                        to="sandbox.sandboxsession",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="sandboxsession",
            index=models.Index(fields=["status"], name="sandbox_ses_status_idx"),
        ),
        migrations.AddIndex(
            model_name="sandboxsession",
            index=models.Index(fields=["mode"], name="sandbox_ses_mode_idx"),
        ),
        migrations.AddIndex(
            model_name="sandboxsnapshot",
            index=models.Index(fields=["session"], name="sandbox_snap_session_idx"),
        ),
        migrations.AddIndex(
            model_name="sandboxartifact",
            index=models.Index(fields=["session"], name="sandbox_art_session_idx"),
        ),
    ]
