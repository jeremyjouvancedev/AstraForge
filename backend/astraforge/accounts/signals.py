from __future__ import annotations

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import IDENTITY_PROVIDER_PASSWORD, UserAccess, Workspace


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_user_access_record(sender, instance, created, **kwargs):
    if not created:
        return
    UserAccess.objects.get_or_create(
        user=instance, defaults={"identity_provider": IDENTITY_PROVIDER_PASSWORD}
    )
    Workspace.ensure_default_for_user(instance)
