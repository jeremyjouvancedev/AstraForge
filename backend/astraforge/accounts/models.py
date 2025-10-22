from __future__ import annotations

import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class ApiKey(models.Model):
    name = models.CharField(max_length=255)
    key_hash = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_keys"
    )
    created_at = models.DateTimeField(default=timezone.now)
    last_used_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "API Key"
        verbose_name_plural = "API Keys"

    @classmethod
    def create_key(cls, *, user, name: str) -> tuple["ApiKey", str]:
        raw_key = secrets.token_urlsafe(32)
        key_hash = _hash_key(raw_key)
        instance = cls.objects.create(user=user, name=name, key_hash=key_hash)
        return instance, raw_key

    @staticmethod
    def hash_raw(raw_key: str) -> str:
        return _hash_key(raw_key)

    def verify(self, raw_key: str) -> bool:
        return secrets.compare_digest(self.key_hash, _hash_key(raw_key))

    def mark_used(self):
        self.last_used_at = timezone.now()
        self.save(update_fields=["last_used_at"])
