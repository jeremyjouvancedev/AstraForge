from django.apps import AppConfig


class RestInterfaceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "astraforge.interfaces.rest"
    verbose_name = "AstraForge REST API"
