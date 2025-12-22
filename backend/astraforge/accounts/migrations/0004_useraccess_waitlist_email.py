from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_useraccess_waitlist"),
    ]

    operations = [
        migrations.AddField(
            model_name="useraccess",
            name="waitlist_notified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
