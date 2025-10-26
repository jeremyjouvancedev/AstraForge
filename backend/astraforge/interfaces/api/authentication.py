from __future__ import annotations

from typing import Optional, Tuple

from rest_framework import authentication, exceptions

from astraforge.accounts.models import ApiKey


class ApiKeyAuthentication(authentication.BaseAuthentication):
    """Authenticates requests using X-Api-Key header."""

    header = "HTTP_X_API_KEY"

    def authenticate(self, request) -> Optional[Tuple[object, None]]:
        raw_key = request.META.get(self.header)
        if not raw_key:
            return None

        key_hash = ApiKey.hash_raw(raw_key)

        try:
            api_key = ApiKey.objects.get(key_hash=key_hash, is_active=True)
        except ApiKey.DoesNotExist:
            raise exceptions.AuthenticationFailed("Invalid API key") from None

        api_key.mark_used()
        return api_key.user, None
