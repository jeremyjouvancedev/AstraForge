from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_workspace_and_members"),
    ]

    operations = [
        migrations.AddField(
            model_name="workspace",
            name="plan",
            field=models.CharField(
                choices=[
                    ("trial", "Trial"),
                    ("pro", "Pro"),
                    ("enterprise", "Enterprise"),
                    ("self_hosted", "Self-hosted"),
                ],
                default="trial",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="workspace",
            name="quota_overrides",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
