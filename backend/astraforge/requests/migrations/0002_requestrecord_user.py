from __future__ import annotations

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("requests", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="requestrecord",
            name="user",
            field=models.ForeignKey(
                on_delete=models.CASCADE,
                related_name="requests",
                to=settings.AUTH_USER_MODEL,
                null=True,
                blank=True,
            ),
        ),
    ]
