from __future__ import annotations

from django.apps import AppConfig


class RequestsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "astraforge.requests"
    verbose_name = "AstraForge Requests"
