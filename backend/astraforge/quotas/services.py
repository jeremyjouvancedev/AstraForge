from __future__ import annotations

from typing import Any, Dict, TYPE_CHECKING

from django.conf import settings
from django.db import transaction
from astraforge.quotas.models import WorkspaceQuotaLedger
from astraforge.sandbox.models import SandboxSession

if TYPE_CHECKING:  # pragma: no cover - hints only
    from astraforge.accounts.models import Workspace


KNOWN_LIMIT_KEYS = {
    "requests_per_month",
    "sandbox_sessions_per_month",
    "sandbox_concurrent",
}


class QuotaExceeded(PermissionError):
    def __init__(self, *, metric: str, limit: int | None, usage: int, message: str):
        super().__init__(message)
        self.metric = metric
        self.limit = limit
        self.usage = usage
        self.message = message


class WorkspaceQuotaService:
    """Evaluate and enforce workspace-level quotas."""

    def __init__(self, django_settings: Any | None = None):
        self._settings = django_settings or settings

    # public API -----------------------------------------------------------------

    def register_request_submission(self, workspace: "Workspace") -> None:
        if not self._should_enforce(workspace):
            return
        limits = self._plan_limits(workspace)
        max_requests = self._coerce_int(limits.get("requests_per_month"))
        if max_requests is None:
            return
        with transaction.atomic():
            ledger = WorkspaceQuotaLedger.for_workspace(workspace, lock=True)
            if ledger.request_count >= max_requests:
                raise self._build_error(
                    workspace,
                    metric="requests_per_month",
                    limit=max_requests,
                    usage=ledger.request_count,
                    template="Workspace '{name}' reached the {limit} monthly request quota.",
                )
            ledger.request_count += 1
            ledger.save(update_fields=["request_count", "updated_at"])

    def register_sandbox_session(self, workspace: "Workspace") -> None:
        if not self._should_enforce(workspace):
            return
        limits = self._plan_limits(workspace)
        concurrent_limit = self._coerce_int(limits.get("sandbox_concurrent"))
        if concurrent_limit is not None and concurrent_limit >= 0:
            active = SandboxSession.objects.filter(
                workspace=workspace,
                status__in=[
                    SandboxSession.Status.STARTING,
                    SandboxSession.Status.READY,
                ],
            ).count()
            if active >= concurrent_limit:
                raise self._build_error(
                    workspace,
                    metric="sandbox_concurrent",
                    limit=concurrent_limit,
                    usage=active,
                    template="Workspace '{name}' has reached the limit of {limit} active sandboxes.",
                )
        monthly_limit = self._coerce_int(limits.get("sandbox_sessions_per_month"))
        if monthly_limit is None:
            return
        with transaction.atomic():
            ledger = WorkspaceQuotaLedger.for_workspace(workspace, lock=True)
            if ledger.sandbox_sessions >= monthly_limit:
                raise self._build_error(
                    workspace,
                    metric="sandbox_sessions_per_month",
                    limit=monthly_limit,
                    usage=ledger.sandbox_sessions,
                    template="Workspace '{name}' has used the {limit} monthly sandbox sessions included in its plan.",
                )
            ledger.sandbox_sessions += 1
            ledger.save(update_fields=["sandbox_sessions", "updated_at"])

    # helpers --------------------------------------------------------------------

    def workspace_limits(self, workspace: "Workspace") -> Dict[str, Any]:
        return self._plan_limits(workspace)

    def plan_catalog(self) -> Dict[str, Dict[str, Any]]:
        defaults = getattr(self._settings, "WORKSPACE_PLAN_LIMITS", {})
        return {key: dict(value) for key, value in defaults.items()}

    def record_sandbox_runtime(self, workspace: "Workspace", seconds: float) -> None:
        duration = int(max(0, seconds))
        if duration <= 0:
            return
        with transaction.atomic():
            ledger = WorkspaceQuotaLedger.for_workspace(workspace, lock=True)
            ledger.sandbox_seconds += duration
            ledger.save(update_fields=["sandbox_seconds", "updated_at"])

    def record_storage_usage(self, workspace: "Workspace", bytes_delta: int) -> None:
        if not bytes_delta:
            return
        with transaction.atomic():
            ledger = WorkspaceQuotaLedger.for_workspace(workspace, lock=True)
            ledger.artifacts_bytes = max(0, ledger.artifacts_bytes + int(bytes_delta))
            ledger.save(update_fields=["artifacts_bytes", "updated_at"])

    def _should_enforce(self, workspace: "Workspace") -> bool:
        enabled = bool(getattr(self._settings, "WORKSPACE_QUOTAS_ENABLED", False))
        if not enabled:
            return False
        if getattr(workspace, "plan", "") == "self_hosted":
            return False
        overrides = workspace.quota_overrides or {}
        if isinstance(overrides, dict) and overrides.get("enforce") is False:
            return False
        return True

    def _plan_limits(self, workspace: "Workspace") -> Dict[str, Any]:
        plan_key = getattr(workspace, "plan", None) or "trial"
        defaults = getattr(self._settings, "WORKSPACE_PLAN_LIMITS", {})
        base = dict(defaults.get(plan_key, defaults.get("trial", {})))
        overrides = workspace.quota_overrides or {}
        limit_overrides = overrides.get("limits") if isinstance(overrides, dict) else {}
        if not isinstance(limit_overrides, dict):
            limit_overrides = {
                key: value
                for key, value in overrides.items()
                if key in KNOWN_LIMIT_KEYS
            }
        for key, value in (limit_overrides or {}).items():
            if key in KNOWN_LIMIT_KEYS:
                base[key] = value
        return base

    @staticmethod
    def _coerce_int(raw: Any) -> int | None:
        if raw is None:
            return None
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        return value if value >= 0 else None

    @staticmethod
    def _build_error(
        workspace: "Workspace",
        *,
        metric: str,
        limit: int | None,
        usage: int,
        template: str,
    ) -> QuotaExceeded:
        message = template.format(name=workspace.name, limit=limit)
        return QuotaExceeded(metric=metric, limit=limit, usage=usage, message=message)


_SERVICE: WorkspaceQuotaService | None = None


def get_quota_service(refresh: bool = False) -> WorkspaceQuotaService:
    global _SERVICE
    if _SERVICE is None or refresh:
        _SERVICE = WorkspaceQuotaService()
    return _SERVICE
