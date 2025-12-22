from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid
import django.utils.timezone


def seed_access_for_existing_users(apps, schema_editor):
    UserAccess = apps.get_model("accounts", "UserAccess")
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    UserModel = apps.get_model(app_label, model_name)
    now = django.utils.timezone.now()
    for user in UserModel.objects.all():
        UserAccess.objects.get_or_create(
            user_id=user.pk,
            defaults={
                "status": "approved",
                "identity_provider": "password",
                "approved_at": now,
                "created_at": now,
                "updated_at": now,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_apikey_uuid_primary_key"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserAccess",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("identity_provider", models.CharField(default="password", max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending approval"),
                            ("approved", "Approved"),
                            ("blocked", "Blocked"),
                        ],
                        default="pending",
                        max_length=32,
                    ),
                ),
                ("notes", models.TextField(blank=True, default="")),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="access",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "User Access",
                "verbose_name_plural": "User Access",
            },
        ),
        migrations.RunPython(
            seed_access_for_existing_users, migrations.RunPython.noop
        ),
    ]
