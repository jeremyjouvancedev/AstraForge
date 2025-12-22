from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sandbox", "0005_add_workspace_fk"),
    ]

    operations = [
        migrations.AddField(
            model_name="sandboxsession",
            name="cpu_seconds",
            field=models.FloatField(default=0),
        ),
        migrations.AddField(
            model_name="sandboxsession",
            name="storage_bytes",
            field=models.BigIntegerField(default=0),
        ),
    ]
