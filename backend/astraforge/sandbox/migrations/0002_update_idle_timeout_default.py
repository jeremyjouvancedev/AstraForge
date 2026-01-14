from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sandbox", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sandboxsession",
            name="idle_timeout_sec",
            field=models.PositiveIntegerField(default=300),
        ),
    ]
