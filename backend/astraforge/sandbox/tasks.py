from __future__ import annotations

"""Celery tasks for sandbox lifecycle management."""

from celery import shared_task

from astraforge.sandbox.reaper import SandboxReaper


@shared_task
def reap_sandboxes() -> dict[str, int]:
    """Terminate sandbox sessions that exceeded idle or lifetime limits."""
    reaper = SandboxReaper()
    return reaper.reap()
