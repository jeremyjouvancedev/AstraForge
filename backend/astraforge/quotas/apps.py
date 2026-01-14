from django.apps import AppConfig


class QuotasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "astraforge.quotas"
    verbose_name = "Workspace Quotas"
