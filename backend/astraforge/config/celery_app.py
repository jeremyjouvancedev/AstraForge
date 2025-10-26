"""Celery application instance for AstraForge."""

from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "astraforge.config.settings")

app = Celery("astraforge")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks(lambda: ["astraforge.application", "astraforge.interfaces"])
