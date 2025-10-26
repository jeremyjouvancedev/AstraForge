"""Custom DRF renderers used by the REST API layer."""

from __future__ import annotations

from rest_framework.renderers import BaseRenderer


class EventStreamRenderer(BaseRenderer):
    """Renderer that negotiates Server-Sent Events responses."""

    media_type = "text/event-stream"
    format = "event-stream"
    charset = None

    def render(self, data, accepted_media_type=None, renderer_context=None):
        # Streaming responses bypass DRF rendering, but we still need to return bytes.
        return data
