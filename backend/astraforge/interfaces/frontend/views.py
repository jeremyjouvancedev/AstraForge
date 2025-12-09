from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404
from django.views.static import serve as static_serve


def frontend_assets(request, path: str):
    """Serve built frontend assets from the Vite dist directory."""
    asset_root = settings.FRONTEND_DIST / "assets"
    return static_serve(request, path, document_root=asset_root)


def frontend_index(request, resource: str = ""):
    """Serve index.html (or another built asset) for all non-API routes."""
    dist_dir = Path(settings.FRONTEND_DIST).resolve()
    if resource:
        candidate = (dist_dir / resource).resolve()
        if candidate.is_file() and candidate.is_relative_to(dist_dir):
            return FileResponse(candidate.open("rb"))

    index_path = (dist_dir / "index.html").resolve()
    if index_path.is_file() and index_path.is_relative_to(dist_dir):
        return FileResponse(index_path.open("rb"))

    raise Http404("Frontend build not found; run pnpm build first.")
