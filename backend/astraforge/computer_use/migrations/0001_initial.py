from __future__ import annotations

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0006_workspace_plan_and_quota_fields"),
        ("sandbox", "0006_add_session_consumption_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="ComputerUseRun",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)),
                ("goal", models.TextField()),
                (
                    "status",
                    models.CharField(
                        max_length=32,
                        choices=[
                            ("running", "Running"),
                            ("awaiting_ack", "Awaiting approval"),
                            ("completed", "Completed"),
                            ("blocked_policy", "Blocked by policy"),
                            ("denied_approval", "Denied approval"),
                            ("timed_out", "Timed out"),
                            ("max_steps", "Max steps"),
                            ("execution_error", "Execution error"),
                            ("user_cancel", "User canceled"),
                            ("failed", "Failed"),
                        ],
                        default="running",
                    ),
                ),
                ("stop_reason", models.CharField(max_length=64, blank=True)),
                ("config", models.JSONField(default=dict, blank=True)),
                ("state", models.JSONField(default=dict, blank=True)),
                ("trace_dir", models.CharField(max_length=512, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "sandbox_session",
                    models.ForeignKey(
                        to="sandbox.sandboxsession",
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="computer_use_runs",
                        null=True,
                        blank=True,
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        to=settings.AUTH_USER_MODEL,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="computer_use_runs",
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        to="accounts.workspace",
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="computer_use_runs",
                        null=True,
                        blank=True,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="computeruserun",
            index=models.Index(fields=["status"], name="computer_use_status_idx"),
        ),
        migrations.AddIndex(
            model_name="computeruserun",
            index=models.Index(fields=["created_at"], name="computer_use_created_idx"),
        ),
    ]
