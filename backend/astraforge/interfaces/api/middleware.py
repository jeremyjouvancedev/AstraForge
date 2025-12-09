"""Middleware helpers for API-layer behavior."""

from __future__ import annotations


class ApiKeyCsrfBypassMiddleware:
    """Disable CSRF checks when an API key header is present.

    DRF enforces CSRF only when session auth runs. This middleware mirrors that intent
    by marking the request as safe when `X-Api-Key` is sent, allowing mixed session/API
    usage on the same endpoints without requiring CSRF cookies for API-key clients.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.META.get("HTTP_X_API_KEY"):
            # Signal CsrfViewMiddleware to skip checks for header-based API clients.
            setattr(request, "_dont_enforce_csrf_checks", True)
        return self.get_response(request)
