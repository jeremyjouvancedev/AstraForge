from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "astraforge.accounts"

    def ready(self):
        # Import signal handlers
        from . import signals  # noqa: F401
