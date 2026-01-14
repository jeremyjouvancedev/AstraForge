from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_workspace_plan_and_quota_fields"),
        ("sandbox", "0004_merge_0002_update_idle_timeout_default_0003_create_snapshot_artifact_tables"),
    ]

    operations = [
        migrations.AddField(
            model_name="sandboxsession",
            name="workspace",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="workspace_sessions",
                to="accounts.workspace",
            ),
        ),
    ]
