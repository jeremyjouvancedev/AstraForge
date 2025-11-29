from __future__ import annotations

import uuid

from django.db import migrations, models


def backfill_api_key_uuid(apps, schema_editor):
    ApiKey = apps.get_model("accounts", "ApiKey")
    for api_key in ApiKey.objects.filter(uuid__isnull=True):
        api_key.uuid = uuid.uuid4()
        api_key.save(update_fields=["uuid"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="apikey",
            name="uuid",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(backfill_api_key_uuid, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="apikey",
            name="id",
        ),
        migrations.RenameField(
            model_name="apikey",
            old_name="uuid",
            new_name="id",
        ),
        migrations.AlterField(
            model_name="apikey",
            name="id",
            field=models.UUIDField(
                default=uuid.uuid4, editable=False, primary_key=True, serialize=False
            ),
        ),
    ]
