from __future__ import annotations

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies: list[tuple[str, str]] = []

    operations = [
        migrations.CreateModel(
            name="RequestRecord",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("tenant_id", models.CharField(max_length=100)),
                ("source", models.CharField(max_length=100)),
                ("sender", models.EmailField(blank=True, max_length=254)),
                ("payload", models.JSONField()),
                ("state", models.CharField(max_length=32)),
                ("artifacts", models.JSONField(default=dict, blank=True)),
                ("metadata", models.JSONField(default=dict, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "astraforge_requests",
                "ordering": ["-created_at"],
            },
        ),
    ]
