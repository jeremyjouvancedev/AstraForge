from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0006_workspace_plan_and_quota_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkspaceQuotaLedger",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("period_start", models.DateField()),
                ("request_count", models.PositiveIntegerField(default=0)),
                ("sandbox_sessions", models.PositiveIntegerField(default=0)),
                ("sandbox_seconds", models.PositiveIntegerField(default=0)),
                ("artifacts_bytes", models.BigIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="quota_ledgers",
                        to="accounts.workspace",
                    ),
                ),
            ],
            options={
                "ordering": ["-period_start", "-updated_at"],
                "unique_together": {("workspace", "period_start")},
            },
        ),
    ]
