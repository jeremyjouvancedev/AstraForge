"""ASGI config for AstraForge."""

from __future__ import annotations

import os
import logging
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "astraforge.config.settings")

# Initialize Django ASGI application early to ensure AppRegistry is ready
django_asgi_app = get_asgi_application()

logger = logging.getLogger(__name__)

async def application(scope, receive, send):
    if scope['type'] == 'http':
        await django_asgi_app(scope, receive, send)
    elif scope['type'] == 'websocket':
        await send({'type': 'websocket.close', 'code': 4003})
    else:
        raise NotImplementedError(f"Unknown scope type {scope['type']}")
