from __future__ import annotations

from datetime import timedelta
import logging
from django.utils import timezone

from astraforge.sandbox.models import SandboxSession
from astraforge.sandbox.services import SandboxOrchestrator

logger = logging.getLogger(__name__)


class SandboxReaper:
    """Identifies and terminates stale sandbox sessions."""

    def __init__(self, orchestrator: SandboxOrchestrator | None = None) -> None:
        self.orchestrator = orchestrator or SandboxOrchestrator()

    def _termination_reason(self, session: SandboxSession, now):
        if session.max_lifetime_sec:
            expiry = session.expires_at or session.created_at + timedelta(seconds=session.max_lifetime_sec)
            if expiry and expiry <= now:
                return "max_lifetime"

        last_seen = session.last_activity_at or session.last_heartbeat_at or session.created_at
        if session.idle_timeout_sec and last_seen:
            idle_deadline = last_seen + timedelta(seconds=session.idle_timeout_sec)
            if idle_deadline <= now:
                return "idle_timeout"
        return None

    def reap(self, *, now=None) -> dict[str, int]:
        now = now or timezone.now()
        terminated = 0
        candidates = list(SandboxSession.objects.filter(status=SandboxSession.Status.READY))
        for session in candidates:
            reason = self._termination_reason(session, now)
            if not reason:
                continue
            logger.info("Terminating stale sandbox session", extra={"id": str(session.id), "reason": reason})
            self.orchestrator.terminate(session, reason=reason)
            terminated += 1
        return {"checked": len(candidates), "terminated": terminated}
