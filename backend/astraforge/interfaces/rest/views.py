"""REST API views for AstraForge."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from datetime import datetime

import logging

from django.conf import settings
from django.contrib.auth import authenticate, login, logout

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from astraforge.accounts import emails as account_emails
from astraforge.accounts.models import (
    ApiKey,
    AccessStatus,
    IDENTITY_PROVIDER_PASSWORD,
    UserAccess,
    Workspace,
    WorkspaceMember,
)
from astraforge.application import tasks as app_tasks
from astraforge.application.use_cases import ApplyPlan, GeneratePlan, SubmitRequest
from astraforge.bootstrap import container, repository
from astraforge.computer_use.models import ComputerUseRun
from astraforge.computer_use.trace import read_timeline_items
from astraforge.domain.models.request import Attachment, Request, RequestPayload
from astraforge.integrations.models import RepositoryLink
from astraforge.interfaces.rest import serializers
from astraforge.interfaces.rest.renderers import EventStreamRenderer
from astraforge.infrastructure.ai.deepagent_runtime import get_deep_agent
from astraforge.infrastructure.ai.serializers import jsonable_chunk, encode_sse
from astraforge.quotas.models import WorkspaceQuotaLedger
from astraforge.quotas.services import QuotaExceeded, get_quota_service
from astraforge.requests.models import RequestRecord
from astraforge.sandbox.models import SandboxSession
from astraforge.sandbox.serializers import SandboxSessionCreateSerializer
from django.http import StreamingHttpResponse
from langchain_core.messages import message_to_dict

logger = logging.getLogger(__name__)

SUPPORTED_IDENTITY_PROVIDERS = ["password"]


def _auth_settings() -> dict[str, object]:
    require_approval = getattr(settings, "AUTH_REQUIRE_APPROVAL", False)
    allow_all_users = getattr(settings, "AUTH_ALLOW_ALL_USERS", False)
    self_hosted = bool(getattr(settings, "SELF_HOSTED", False))
    billing_enabled = bool(getattr(settings, "BILLING_ENABLED", not self_hosted))
    waitlist_enabled = bool(
        getattr(
            settings,
            "AUTH_WAITLIST_ENABLED",
            require_approval and not allow_all_users,
        )
    )
    if allow_all_users or not require_approval:
        waitlist_enabled = False
    return {
        "require_approval": require_approval,
        "allow_all_users": allow_all_users,
        "waitlist_enabled": waitlist_enabled,
        "self_hosted": self_hosted,
        "billing_enabled": billing_enabled,
        "supported_providers": SUPPORTED_IDENTITY_PROVIDERS,
    }


def _identity_provider_from_request(request) -> str:
    try:
        raw_provider = request.data.get("identity_provider", "")
    except Exception:
        raw_provider = ""
    provider = str(raw_provider or "").strip() or IDENTITY_PROVIDER_PASSWORD
    return provider


def _serialize_access(access: UserAccess) -> dict[str, object]:
    payload = access.to_dict()
    payload["waitlist_enforced"] = _auth_settings()["waitlist_enabled"]
    return payload


def _serialize_user(user, *, access: UserAccess | None = None) -> dict[str, object]:
    access_obj = access or UserAccess.for_user(user)
    memberships = (
        WorkspaceMember.objects.filter(user=user)
        .select_related("workspace")
        .order_by("joined_at")
    )
    workspaces = [
        {
            "uid": member.workspace.uid,
            "name": member.workspace.name,
            "role": member.role,
        }
        for member in memberships
    ]
    return {
        "username": user.username,
        "email": user.email,
        "access": _serialize_access(access_obj),
        "workspaces": workspaces,
        "default_workspace": workspaces[0]["uid"] if workspaces else None,
    }


class RequestViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    serializer_class = serializers.RequestSerializer
    lookup_field = "id"

    def create(self, request, *args, **kwargs):
        allowed_workspaces = Workspace.allowed_uids_for_user(request.user)
        if not allowed_workspaces:
            raise PermissionDenied("Join a workspace before submitting requests.")
        if not RepositoryLink.objects.filter(
            workspace__uid__in=allowed_workspaces
        ).exists():
            raise PermissionDenied(
                "Link a project in one of your workspaces before submitting requests."
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_obj = serializer.save()
        try:
            SubmitRequest(repository=repository)(request_obj)
        except PermissionError as exc:
            raise PermissionDenied(str(exc)) from exc
        container.resolve_run_log().publish(
            str(request_obj.id),
            {
                "type": "user_prompt",
                "request_id": str(request_obj.id),
                "message": request_obj.payload.description,
            },
        )
        app_tasks.execute_request_task.delay(str(request_obj.id))
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    def list(self, request, *args, **kwargs):
        allowed_uids = Workspace.allowed_uids_for_user(request.user)
        tenant_id = request.query_params.get("tenant_id")
        if tenant_id and tenant_id not in allowed_uids:
            raise PermissionDenied("You do not have access to this workspace.")
        items = repository.list(user_id=str(request.user.id))
        if allowed_uids:
            items = [
                item
                for item in items
                if item.tenant_id in allowed_uids
                and (not tenant_id or item.tenant_id == tenant_id)
            ]
        else:
            items = []
        serializer = self.get_serializer(items, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="execute")
    def execute(self, request, id=None):
        serializer = serializers.ExecuteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_id = str(id)
        allowed_uids = Workspace.allowed_uids_for_user(request.user)
        try:
            request_obj = repository.get(request_id, user_id=str(request.user.id))
        except KeyError as exc:
            raise NotFound(f"Request {request_id} not found") from exc
        if request_obj.tenant_id not in allowed_uids:
            raise PermissionDenied("You do not have access to this workspace.")
        llm_provider = (serializer.validated_data.get("llm_provider") or "").strip().lower()
        llm_model = (serializer.validated_data.get("llm_model") or "").strip()
        reasoning_effort = (serializer.validated_data.get("reasoning_effort") or "").strip().lower()
        if llm_provider or llm_model or reasoning_effort:
            llm_config: dict[str, str] = {}
            existing_llm = request_obj.metadata.get("llm")
            if isinstance(existing_llm, dict):
                llm_config.update({k: str(v) for k, v in existing_llm.items()})
            if llm_provider:
                llm_config["provider"] = llm_provider
            if llm_model:
                llm_config["model"] = llm_model
            if reasoning_effort:
                llm_config["reasoning_effort"] = reasoning_effort
            request_obj.metadata["llm"] = llm_config
            repository.save(request_obj)
        app_tasks.execute_request_task.delay(request_id)
        return Response({"status": "queued"}, status=status.HTTP_202_ACCEPTED)

    def get_object(self):
        from django.http import Http404

        request_id = self.kwargs[self.lookup_field]
        try:
            obj = repository.get(str(request_id), user_id=str(self.request.user.id))
        except KeyError as exc:  # pragma: no cover - fallback
            raise Http404(f"Request {request_id} not found") from exc
        allowed_uids = Workspace.allowed_uids_for_user(self.request.user)
        if obj.tenant_id not in allowed_uids and obj.user_id != str(
            self.request.user.id
        ):
            raise PermissionDenied("You do not have access to this workspace.")
        return obj


class ChatViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = serializers.ChatSerializer

    def create(self, request, *args, **kwargs):  # pragma: no cover - stub
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_id = str(serializer.validated_data["request_id"])
        message_content = serializer.validated_data["message"]
        attachments_data = serializer.validated_data.get("attachments", [])
        run_log = container.resolve_run_log()

        # Convert raw attachment data to Attachment objects for domain model
        domain_attachments = [
            Attachment(
                uri=att.get("uri", ""),
                name=att.get("name", ""),
                content_type=att.get("content_type", ""),
            )
            for att in attachments_data
        ]

        try:
            request_obj = repository.get(request_id, user_id=str(request.user.id))
        except KeyError:
            if RequestRecord.objects.filter(id=request_id).exists():
                raise PermissionDenied("Request not found")
            workspace = Workspace.resolve_for_user(request.user, preferred_uid=None)
            quota_service = get_quota_service()
            try:
                quota_service.register_request_submission(workspace)
            except QuotaExceeded as exc:
                raise PermissionDenied(str(exc)) from exc
            payload = RequestPayload(
                title=message_content.strip() or "User message",
                description=message_content,
                context={},
                attachments=domain_attachments,
            )
            request_obj = Request(
                id=request_id,
                user_id=str(request.user.id),
                tenant_id=workspace.uid,
                source="direct_user",
                sender="",
                payload=payload,
                metadata={},
            )
            repository.save(request_obj)
        else:
            allowed_uids = Workspace.allowed_uids_for_user(request.user)
            if request_obj.tenant_id not in allowed_uids:
                raise PermissionDenied("You do not have access to this workspace.")

        messages = list(request_obj.metadata.get("chat_messages", []))
        new_message = {
            "role": "user",
            "message": message_content,
            "created_at": timezone.now().isoformat(),
        }
        if attachments_data:
            new_message["attachments"] = attachments_data
        messages.append(new_message)
        request_obj.metadata["chat_messages"] = messages
        try:
            repository.save(request_obj)
        except PermissionError as exc:
            raise PermissionDenied(str(exc)) from exc
        app_tasks.execute_request_task.delay(request_id)
        run_log_payload = {
            "type": "user_message",
            "request_id": request_id,
            "message": message_content,
        }
        if attachments_data:
            run_log_payload["attachments"] = attachments_data
        run_log.publish(request_id, run_log_payload)
        return Response({"status": "received"}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):  # pragma: no cover - stub
        request_id = str(pk)
        app_tasks.submit_merge_request_task.delay(request_id)
        return Response({"status": "queued"}, status=status.HTTP_202_ACCEPTED)


class WorkspaceViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsAuthenticated]
    serializer_class = serializers.WorkspaceSerializer
    lookup_field = "uid"

    def get_queryset(self):
        return Workspace.objects.filter(members__user=self.request.user).distinct()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        output = self.get_serializer(instance).data
        headers = self.get_success_headers(output)
        return Response(output, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=["get"], url_path="usage")
    def usage(self, request, uid=None):
        workspace = self.get_object()
        quota_service = get_quota_service()
        ledger = WorkspaceQuotaLedger.for_workspace(workspace)
        limits = quota_service.workspace_limits(workspace)
        active_sandboxes = SandboxSession.objects.filter(
            workspace=workspace,
            status__in=[
                SandboxSession.Status.READY,
                SandboxSession.Status.STARTING,
            ],
        ).count()
        payload = {
            "plan": workspace.plan,
            "limits": limits,
            "usage": {
                "requests_per_month": ledger.request_count,
                "sandbox_sessions_per_month": ledger.sandbox_sessions,
                "active_sandboxes": active_sandboxes,
                "sandbox_seconds": ledger.sandbox_seconds,
                "artifacts_bytes": ledger.artifacts_bytes,
            },
            "period_start": ledger.period_start.isoformat(),
            "catalog": quota_service.plan_catalog(),
        }
        return Response(payload)


class RunLogStreamView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [EventStreamRenderer]

    def get(self, request, pk):  # pragma: no cover - SSE placeholder
        request_id = str(pk)
        try:
            repository.get(request_id, user_id=str(request.user.id))
        except KeyError as exc:
            raise NotFound("Request not found") from exc
        run_log = container.resolve_run_log()

        def event_stream():
            handshake = {
                "request_id": request_id,
                "type": "heartbeat",
                "message": "stream_ready",
            }
            yield "event: message\n"
            yield "data: " + json.dumps(handshake) + "\n\n"
            for event in run_log.stream(request_id):
                yield "event: message\n"
                yield "data: " + json.dumps(event) + "\n\n"

        response = StreamingHttpResponse(
            event_stream(), content_type="text/event-stream"
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


class ComputerUseRunViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        runs = ComputerUseRun.objects.filter(user=request.user).order_by("-created_at")
        data = [self._serialize_run(run) for run in runs]
        serializer = serializers.ComputerUseRunSerializer(data, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        run = self._get_run_or_404(request, pk)
        serializer = serializers.ComputerUseRunSerializer(self._serialize_run(run))
        return Response(serializer.data)

    def create(self, request):
        serializer = serializers.ComputerUseRunCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        goal = str(payload.get("goal") or "").strip()
        if not goal:
            return Response({"detail": "goal is required"}, status=status.HTTP_400_BAD_REQUEST)

        decision_provider = (
            (payload.get("decision_provider") or "").strip().lower() or "scripted"
        )
        decision_script = payload.get("decision_script") or []
        config = dict(payload.get("config") or {})
        config.setdefault("decision_provider", decision_provider)
        if decision_script:
            config["decision_script"] = decision_script

        session = self._resolve_sandbox_session(request, payload)

        run = ComputerUseRun.objects.create(
            user=request.user,
            workspace=session.workspace if session else None,
            sandbox_session=session,
            goal=goal,
            config=config,
        )
        try:
            app_tasks.computer_use_run_task.delay(str(run.id))
        except Exception as exc:  # noqa: BLE001
            run.status = ComputerUseRun.Status.FAILED
            run.stop_reason = "failed"
            run.save(update_fields=["status", "stop_reason", "updated_at"])
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        output = self._serialize_run(run)
        response_serializer = serializers.ComputerUseRunSerializer(output)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="acknowledge")
    def acknowledge(self, request, pk=None):
        run = self._get_run_or_404(request, pk)
        if run.status != ComputerUseRun.Status.AWAITING_ACK:
            return Response(
                {"detail": "Run is not awaiting approval."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = serializers.ComputerUseRunAckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        decision = serializer.validated_data["decision"]
        acknowledged = serializer.validated_data.get("acknowledged") or []
        pending_checks = (run.state or {}).get("pending_checks") or []
        pending_ids = {str(item.get("id")) for item in pending_checks if item.get("id")}
        if decision == "approve" and pending_ids and not pending_ids.issubset(set(acknowledged)):
            return Response(
                {"detail": "All pending safety checks must be acknowledged."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            app_tasks.computer_use_ack_task.delay(
                str(run.id),
                decision=decision,
                acknowledged=acknowledged,
            )
        except Exception as exc:  # noqa: BLE001
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if decision == "approve":
            run.status = ComputerUseRun.Status.RUNNING
            run.stop_reason = ""
        else:
            run.status = ComputerUseRun.Status.DENIED_APPROVAL
            run.stop_reason = "denied_approval"
        run.updated_at = timezone.now()
        run.save(update_fields=["status", "stop_reason", "updated_at"])

        output = self._serialize_run(run)
        response_serializer = serializers.ComputerUseRunSerializer(output)
        return Response(response_serializer.data)

    @action(detail=True, methods=["get"], url_path="timeline")
    def timeline(self, request, pk=None):
        run = self._get_run_or_404(request, pk)
        trace_dir = str(run.trace_dir or "").strip()
        if not trace_dir:
            return Response({"items": []})

        trace_root = Path(
            os.getenv("COMPUTER_USE_TRACE_DIR", "/var/lib/astraforge/computer-use")
        ).resolve()
        trace_path = Path(trace_dir).resolve()
        allowed_roots = {trace_root, Path("/tmp/astraforge-computer-use").resolve()}
        if not any(
            trace_path == root or root in trace_path.parents for root in allowed_roots
        ):
            return Response(
                {"detail": "Trace directory is outside the allowed root."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw_limit = request.query_params.get("limit")
        limit: int | None = None
        if raw_limit:
            try:
                limit = int(raw_limit)
            except ValueError:
                return Response(
                    {"detail": "limit must be an integer"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if limit <= 0:
                return Response({"items": []})

        include_screenshots = str(
            request.query_params.get("include_screenshots", "")
        ).strip().lower() in {"1", "true", "yes"}

        items = read_timeline_items(
            trace_path, limit=limit, include_screenshots=include_screenshots
        )
        return Response({"items": items})

    def _get_run_or_404(self, request, pk=None) -> ComputerUseRun:
        try:
            return ComputerUseRun.objects.get(id=pk, user=request.user)
        except ComputerUseRun.DoesNotExist as exc:
            raise NotFound("Computer-use run not found") from exc

    def _resolve_sandbox_session(self, request, payload) -> SandboxSession:
        expected_image = os.getenv("COMPUTER_USE_IMAGE", "astraforge/computer-use:latest").strip()
        session_id = payload.get("sandbox_session_id")
        if session_id:
            session = SandboxSession.objects.filter(id=session_id, user=request.user).first()
            if not session:
                raise NotFound("Sandbox session not found")
            if expected_image and session.image != expected_image:
                raise ValidationError(
                    {
                        "sandbox_session_id": [
                            f"Sandbox session image must match {expected_image} for computer-use."
                        ]
                    }
                )
            return session

        sandbox_payload = dict(payload.get("sandbox") or {})
        if not sandbox_payload.get("image"):
            sandbox_payload["image"] = expected_image
        metadata = dict(sandbox_payload.get("metadata") or {})
        metadata.setdefault("purpose", "computer_use")
        sandbox_payload["metadata"] = metadata
        create_serializer = SandboxSessionCreateSerializer(
            data=sandbox_payload,
            context={"request": request},
        )
        create_serializer.is_valid(raise_exception=True)
        session = create_serializer.save()
        return session

    def _serialize_run(self, run: ComputerUseRun, *, result=None) -> dict[str, object]:
        state = dict(run.state or {})
        pending_checks = state.get("pending_checks") or []
        if result is not None and getattr(result, "pending_checks", None):
            pending_checks = result.pending_checks
        if run.status != ComputerUseRun.Status.AWAITING_ACK:
            pending_checks = []
        return {
            "id": run.id,
            "goal": run.goal,
            "final_response": run.final_response,
            "status": run.status,
            "stop_reason": run.stop_reason or "",
            "trace_dir": run.trace_dir or "",
            "sandbox_session_id": run.sandbox_session_id,
            "pending_checks": pending_checks,
            "step_index": state.get("step_index", 0),
            "created_at": run.created_at,
            "updated_at": run.updated_at,
        }


class DeepAgentConversationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # For now we align conversation IDs with sandbox session IDs
        from astraforge.sandbox.serializers import (
            SandboxSessionCreateSerializer,
            SandboxSessionSerializer,
        )
        from astraforge.sandbox.services import (
            SandboxOrchestrator,
            SandboxProvisionError,
        )

        create_serializer = SandboxSessionCreateSerializer(
            data=request.data or {},
            context={"request": request},
        )
        create_serializer.is_valid(raise_exception=True)
        session = create_serializer.save()
        orchestrator = SandboxOrchestrator()
        try:
            orchestrator.provision(session)
        except SandboxProvisionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        session_data = SandboxSessionSerializer(session).data
        payload = {
            "conversation_id": session_data["id"],
            "sandbox_session_id": session_data["id"],
            "status": session_data["status"],
        }
        return Response(payload, status=status.HTTP_201_CREATED)


class DeepAgentMessageView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id: str):
        from astraforge.sandbox.services import (
            SandboxOrchestrator,
            SandboxProvisionError,
        )

        try:
            session = SandboxSession.objects.get(id=conversation_id, user=request.user)
        except SandboxSession.DoesNotExist:
            raise NotFound("Sandbox session not found for this conversation")

        workspace_root = session.workspace_path or "/workspace"
        workspace_path_pattern = re.compile(
            rf"({re.escape(workspace_root)}/[^\s'\"`]+)"
        )
        sandbox_link_pattern = re.compile(
            r"\[(?P<label>[^\]]+)\]\(sandbox:(?P<path>[^\)]+)\)"
        )
        sandbox_path_pattern = re.compile(
            r"sandbox:(?P<path>(?:workspace/|/workspace/)[^\)\s'\"`]+)"
        )
        orchestrator = SandboxOrchestrator()
        exported_paths: dict[str, dict[str, object]] = {}

        def _export_path(raw_path: str) -> dict[str, object] | None:
            # Normalize relative /workspace references from sandbox: links or plain paths.
            path = raw_path.strip()
            if not path:
                return None
            # Allow both workspace/… and /workspace/… in the sandbox: scheme.
            if path.startswith("/workspace/"):
                abs_path = path
            elif path.startswith("workspace/"):
                abs_path = f"{workspace_root.rstrip('/')}/{path[len('workspace/'):]}"
            else:
                abs_path = f"{workspace_root.rstrip('/')}/{path.lstrip('/')}"

            if abs_path in {
                workspace_root,
                f"{workspace_root}/.",
                f"{workspace_root}/..",
            }:
                return None
            if abs_path in exported_paths:
                return exported_paths[abs_path]

            filename = abs_path.rsplit("/", 1)[-1] or "artifact"
            try:
                artifact = orchestrator.export_file(
                    session,
                    path=abs_path,
                    filename=filename,
                    content_type="application/octet-stream",
                )
            except SandboxProvisionError:
                return None
            # Prefer the artifact's download_url if it is configured; otherwise
            # fall back to a direct API endpoint that streams file bytes.
            url = str(artifact.download_url or "").strip()
            if not url:
                from urllib.parse import quote

                encoded_path = quote(abs_path, safe="/")
                encoded_filename = quote(filename, safe="")
                url = (
                    f"/api/sandbox/sessions/{session.id}/files/content/"
                    f"?path={encoded_path}&filename={encoded_filename}"
                )
            artifact_dict: dict[str, object] = {
                "id": str(artifact.id),
                "filename": artifact.filename,
                "download_url": url,
                "storage_path": artifact.storage_path,
                "content_type": artifact.content_type,
                "size_bytes": artifact.size_bytes,
            }
            exported_paths[abs_path] = artifact_dict
            return artifact_dict

        def export_artifacts_from_text(
            text: str | None, *, allow_workspace_paths: bool = False
        ) -> list[dict[str, object]]:
            if not text:
                return []
            matches: list[str] = []
            if "sandbox:" in text:
                matches.extend(sandbox_path_pattern.findall(text))
            if allow_workspace_paths and workspace_root in text:
                matches.extend(workspace_path_pattern.findall(text))
            if not matches:
                return []
            artifacts: list[dict[str, object]] = []
            seen: set[str] = set()
            for path in matches:
                artifact_dict = _export_path(path)
                if artifact_dict is None:
                    continue
                key = str(
                    artifact_dict.get("id")
                    or artifact_dict.get("storage_path")
                    or artifact_dict.get("download_url")
                    or path
                )
                if key in seen:
                    continue
                seen.add(key)
                artifacts.append(artifact_dict)
            return artifacts

        def rewrite_sandbox_links(text: str | None) -> str:
            """Replace [label](sandbox:workspace/...) with real download URLs."""
            if not text or "sandbox:" not in text:
                return text or ""

            def _replacer(match: re.Match[str]) -> str:
                label = match.group("label")
                raw_path = match.group("path")
                artifact = _export_path(raw_path)
                if not artifact:
                    return match.group(0)
                url = str(artifact.get("download_url") or "")
                if not url:
                    return match.group(0)
                # Add a hint query param so the frontend can treat it as a download link.
                url = f"{url}{'&' if '?' in url else '?'}download=1"
                return f"[{label}]({url})"

            return sandbox_link_pattern.sub(_replacer, text)

        serializer = serializers.DeepAgentMessageRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        messages_payload = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in serializer.validated_data["messages"]
        ]
        stream = serializer.validated_data.get("stream", True)
        
        llm_config = {}
        if serializer.validated_data.get("llm_provider"):
            llm_config["provider"] = serializer.validated_data["llm_provider"]
        if serializer.validated_data.get("llm_model"):
            llm_config["model"] = serializer.validated_data["llm_model"]
        if serializer.validated_data.get("reasoning_effort"):
            llm_config["reasoning_effort"] = serializer.validated_data["reasoning_effort"]
        if serializer.validated_data.get("reasoning_check") is not None:
            llm_config["reasoning_check"] = serializer.validated_data["reasoning_check"]

        from astraforge.domain.models.request import Request as DomainRequest
        from astraforge.domain.models.request import RequestPayload
        
        dummy_request = DomainRequest(
            id=str(conversation_id),
            source="chat_view",
            sender=str(request.user.email or request.user.username),
            payload=RequestPayload(title="chat", description="chat", context={}),
            metadata={"llm": llm_config} if llm_config else {},
            user_id=str(request.user.id),
            tenant_id="chat",
        )
        
        config = {
            "thread_id": str(conversation_id),
            "configurable": {
                "sandbox_session_id": str(conversation_id),
            },
        }
        agent = get_deep_agent(dummy_request)

        if not stream:
            try:
                result = agent.invoke({"messages": messages_payload}, config=config)
            except Exception as exc:  # noqa: BLE001
                raise APIException(str(exc)) from exc  # pragma: no cover - error path
            normalized = jsonable_chunk(result)
            return Response(normalized)

        seen_tool_call_ids: set[str] = set()
        seen_tool_result_ids: set[str] = set()

        def _normalize_messages(raw: object) -> list[object]:
            if isinstance(raw, dict):
                msgs = raw.get("messages", []) or []
            else:
                msgs = []
            if not isinstance(msgs, list):
                return []
            return msgs

        def _to_message_dict(msg: object) -> dict[str, object]:
            try:
                return message_to_dict(msg)  # type: ignore[arg-type]
            except Exception:
                pass
            if isinstance(msg, dict):
                return msg
            return jsonable_chunk(msg)

        def _content_to_text(content: object) -> str:
            if isinstance(content, list):
                parts: list[str] = []
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    text_value = part.get("text")
                    if isinstance(text_value, str):
                        parts.append(text_value)
                        continue
                    if (part.get("type") == "image_url") and isinstance(
                        part.get("image_url"), dict
                    ):
                        image_dict = part["image_url"]
                        url = image_dict.get("url")
                        if isinstance(url, str) and url:
                            alt = image_dict.get("alt") or "sandbox image"
                            parts.append(f"![{alt}]({url})")
                return "\n\n".join(parts)
            if content is None:
                return ""
            return str(content)

        def iter_new_tool_calls(
            messages: list[object], seen_ids: set[str]
        ) -> list[tuple[str, str, object]]:
            found: list[tuple[str, str, object]] = []
            for raw in messages:
                msg = _to_message_dict(raw)
                data = msg.get("data") or {}
                if not isinstance(data, dict):
                    continue
                tool_calls = data.get("tool_calls") or []
                if not isinstance(tool_calls, list):
                    continue
                for call in tool_calls:
                    if not isinstance(call, dict):
                        continue
                    name = (
                        call.get("name")
                        or call.get("tool")
                        or (call.get("function") or {}).get("name")
                    )
                    if not name:
                        continue
                    call_id = (
                        call.get("id")
                        or call.get("tool_call_id")
                        or (call.get("function") or {}).get("id")
                        or str(name)
                    )
                    if call_id in seen_ids:
                        continue
                    seen_ids.add(call_id)
                    args = (
                        call.get("args")
                        or call.get("arguments")
                        or call.get("input")
                        or (call.get("function") or {}).get("arguments")
                    )
                    found.append((str(call_id), str(name), args))
            return found

        def iter_new_tool_results(
            messages: list[object], seen_ids: set[str]
        ) -> list[dict[str, object]]:
            results: list[dict[str, object]] = []
            for raw in messages:
                msg = _to_message_dict(raw)
                msg_type = msg.get("type")
                if not msg_type or str(msg_type).lower() not in {"tool", "tool_message"}:
                    continue
                data = msg.get("data") or {}
                if not isinstance(data, dict):
                    continue
                tool_name = data.get("name") or data.get("tool_name") or data.get("tool")
                tool_call_id = data.get("tool_call_id") or data.get("id") or tool_name
                if tool_call_id and str(tool_call_id) in seen_ids:
                    continue
                if tool_call_id:
                    seen_ids.add(str(tool_call_id))

                content = data.get("content")
                raw_content_text = _content_to_text(content)
                content_text = rewrite_sandbox_links(raw_content_text)
                artifacts_from_data = data.get("artifacts")
                tool_name_normalized = str(tool_name or "").lower()
                auto_artifacts = export_artifacts_from_text(
                    raw_content_text,
                    allow_workspace_paths=tool_name_normalized
                    in {"write_file", "edit_file", "ls"},
                )
                combined_artifacts: list[dict[str, object]] = []
                if artifacts_from_data:
                    if isinstance(artifacts_from_data, list):
                        combined_artifacts.extend(
                            [a for a in artifacts_from_data if isinstance(a, dict)]
                        )
                    elif isinstance(artifacts_from_data, dict):
                        combined_artifacts.append(artifacts_from_data)
                if auto_artifacts:
                    combined_artifacts.extend(auto_artifacts)

                result: dict[str, object] = {
                    "tool_call_id": str(tool_call_id) if tool_call_id else None,
                    "tool_name": str(tool_name) if tool_name else None,
                    "output": content_text,
                }
                if combined_artifacts:
                    if len(combined_artifacts) == 1:
                        result["artifacts"] = combined_artifacts[0]
                    else:
                        result["artifacts"] = combined_artifacts
                results.append(result)
            return results

        def messages_to_dict(messages: list[object]) -> list[dict[str, object]]:
            return [_to_message_dict(msg) for msg in messages]

        def event_stream():
            try:
                for chunk in agent.stream(
                    {"messages": messages_payload},
                    config=config,
                    stream_mode="values",
                ):
                    messages = _normalize_messages(chunk)

                    for tc_id, tool_name, args in iter_new_tool_calls(
                        messages, seen_tool_call_ids
                    ):
                        tool_start_payload = {
                            "event": "tool_start",
                            "data": {
                                "tool_call_id": tc_id,
                                "tool_name": tool_name,
                                "args": args,
                            },
                        }
                        yield encode_sse(tool_start_payload)

                    for result in iter_new_tool_results(messages, seen_tool_result_ids):
                        tool_result_payload = {
                            "event": "tool_result",
                            "data": result,
                        }
                        yield encode_sse(tool_result_payload)

                    if not messages:
                        continue
                    last_msg = messages[-1]
                    last_msg_dict = messages_to_dict([last_msg])[0]
                    msg_payload = {
                        "event": "delta",
                        "data": last_msg_dict,
                    }
                    yield encode_sse(msg_payload)
            except Exception as exc:  # noqa: BLE001
                error_payload = {"error": str(exc)}
                yield encode_sse(error_payload)

        response = StreamingHttpResponse(
            event_stream(), content_type="text/event-stream"
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


def _coerce_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = parse_datetime(value)
        if parsed is None:
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError:
                return None
    else:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_default_timezone())
    return parsed


class ActivityLogViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        user_id = str(request.user.id)
        allowed_uids = Workspace.allowed_uids_for_user(request.user)
        tenant_id = request.query_params.get("tenant_id")
        if tenant_id and tenant_id not in allowed_uids:
            raise PermissionDenied("You do not have access to this workspace.")

        requests = repository.list(user_id=user_id)
        if allowed_uids:
            requests = [
                item
                for item in requests
                if item.tenant_id in allowed_uids
                and (not tenant_id or item.tenant_id == tenant_id)
            ]
        else:
            requests = []

        request_ordinals = self._build_request_ordinals(requests)
        runs = self._collect_runs(requests)
        merge_requests = self._collect_merge_requests(requests)
        sessions = self._collect_sandbox_sessions(request.user, allowed_uids, tenant_id)
        sandbox_ordinals = self._build_sandbox_ordinals(sessions)

        events: list[dict[str, object]] = []
        summary = {
            "total": 0,
            "requests": 0,
            "runs": 0,
            "merges": 0,
            "sandboxes": 0,
        }

        def add_event(
            event_type: str, timestamp_value: object, payload: dict[str, object]
        ) -> None:
            parsed = _coerce_datetime(timestamp_value)
            if not parsed:
                return
            payload["timestamp"] = parsed.isoformat()
            payload["_sort_key"] = parsed
            payload["type"] = event_type
            events.append(payload)
            if event_type == "Request":
                summary["requests"] += 1
            elif event_type == "Run":
                summary["runs"] += 1
            elif event_type == "Merge":
                summary["merges"] += 1
            elif event_type == "Sandbox":
                summary["sandboxes"] += 1

        for request_obj in requests:
            created_at = request_obj.created_at
            if not created_at:
                continue
            project_meta = request_obj.metadata.get("project") or {}
            repository_name = (
                project_meta.get("repository")
                if isinstance(project_meta, dict)
                else None
            )
            add_event(
                "Request",
                created_at,
                {
                    "id": f"request-{request_obj.id}",
                    "title": request_obj.payload.title or "New automation request",
                    "description": (
                        f"Captured for {repository_name}"
                        if repository_name
                        else "Request captured in AstraForge."
                    ),
                    "href": f"/app/requests/{request_obj.id}/run",
                    "consumption": {
                        "kind": "request",
                        "ordinal": request_ordinals.get(str(request_obj.id)),
                    },
                },
            )

        for run in runs:
            timestamp = run.get("started_at") or run.get("finished_at")
            if not timestamp:
                continue
            status = str(run.get("status") or "queued").lower()
            request_title = str(run.get("request_title") or "")
            description = (
                f'Automation for "{request_title}"'
                if request_title
                else "Automation run kicked off."
            )
            add_event(
                "Run",
                timestamp,
                {
                    "id": f"run-{run.get('id')}",
                    "title": f"Run {status}",
                    "description": description,
                    "href": f"/app/requests/{run.get('request_id')}/run",
                },
            )

        for mr in merge_requests:
            created_at = mr.get("created_at")
            if not created_at:
                continue
            target_branch = str(mr.get("target_branch") or "")
            description = (
                f"Targeting {target_branch}"
                if target_branch
                else "Merge request created by AstraForge."
            )
            add_event(
                "Merge",
                created_at,
                {
                    "id": f"merge-{mr.get('id')}",
                    "title": str(mr.get("title") or "Merge request opened"),
                    "description": description,
                    "href": f"/app/requests/{mr.get('request_id')}/run",
                },
            )

        for session in sessions:
            timestamp = session.updated_at or session.created_at
            if not timestamp:
                continue
            add_event(
                "Sandbox",
                timestamp,
                {
                    "id": f"sandbox-{session.id}",
                    "title": f"Sandbox {session.status}",
                    "description": f"Mode: {session.mode}",
                    "consumption": {
                        "kind": "sandbox",
                        "ordinal": sandbox_ordinals.get(str(session.id)),
                        "cpu_seconds": session.cpu_seconds,
                        "storage_bytes": session.storage_bytes,
                    },
                },
            )

        events.sort(key=lambda item: item["_sort_key"], reverse=True)
        for event in events:
            event.pop("_sort_key", None)
        summary["total"] = len(events)

        page, page_size = self._get_pagination(request)
        start = (page - 1) * page_size
        end = start + page_size
        paged = events[start:end]
        next_page = page + 1 if end < len(events) else None
        prev_page = page - 1 if page > 1 else None
        serializer = serializers.ActivityEventSerializer(paged, many=True)
        return Response(
            {
                "count": len(events),
                "page": page,
                "page_size": page_size,
                "next_page": next_page,
                "previous_page": prev_page,
                "results": serializer.data,
                "summary": summary,
            }
        )

    def _build_request_ordinals(self, requests: list[Request]) -> dict[str, int]:
        ordered = sorted(requests, key=lambda item: item.created_at or timezone.now())
        return {str(item.id): index + 1 for index, item in enumerate(ordered)}

    def _collect_runs(self, requests: list[Request]) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        run_view = RunViewSet()
        for request_obj in requests:
            runs_meta = list(request_obj.metadata.get("runs", []) or [])
            if not runs_meta:
                fallback = run_view._fallback_run(request_obj)
                if fallback is not None:
                    runs_meta = [fallback]
            for run in runs_meta:
                entry = run_view._build_run_entry(request_obj, run, include_events=False)
                if entry is not None:
                    items.append(entry)
        return items

    def _collect_merge_requests(self, requests: list[Request]) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        merge_view = MergeRequestViewSet()
        for request_obj in requests:
            metadata_mr = request_obj.metadata.get("mr") or {}
            if not metadata_mr:
                continue
            entry = merge_view._build_entry(request_obj, metadata_mr)
            items.append(entry)
        return items

    def _collect_sandbox_sessions(
        self,
        user,
        allowed_uids: list[str],
        tenant_id: str | None,
    ) -> list[SandboxSession]:
        sessions = SandboxSession.objects.filter(user=user)
        if tenant_id:
            sessions = sessions.filter(workspace__uid=tenant_id)
        elif allowed_uids:
            sessions = sessions.filter(workspace__uid__in=allowed_uids)
        return list(sessions)

    def _build_sandbox_ordinals(
        self, sessions: list[SandboxSession]
    ) -> dict[str, int]:
        ordered = sorted(
            (session for session in sessions if session.created_at or session.updated_at),
            key=lambda item: item.created_at or item.updated_at or timezone.now(),
        )
        return {str(item.id): index + 1 for index, item in enumerate(ordered)}

    @staticmethod
    def _get_pagination(request) -> tuple[int, int]:
        def parse_int(value: object, default: int) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        page = max(parse_int(request.query_params.get("page"), 1), 1)
        page_size = parse_int(request.query_params.get("page_size"), 25)
        if page_size < 1:
            page_size = 25
        if page_size > 100:
            page_size = 100
        return page, page_size


class RunViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        runs = self._collect_runs(include_events=False, user_id=str(request.user.id))
        serializer = serializers.RunSummarySerializer(runs, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        run_id = str(pk) if pk is not None else ""
        runs = self._collect_runs(include_events=True, user_id=str(request.user.id))
        for run in runs:
            if run["id"] == run_id:
                serializer = serializers.RunDetailSerializer(run)
                return Response(serializer.data)
        raise NotFound("Run not found")

    def _collect_runs(self, *, include_events: bool, user_id: str) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        for request_obj in repository.list(user_id=user_id):
            runs_meta = list(request_obj.metadata.get("runs", []) or [])
            if not runs_meta:
                fallback = self._fallback_run(request_obj)
                if fallback is not None:
                    runs_meta = [fallback]
            for run in runs_meta:
                entry = self._build_run_entry(
                    request_obj, run, include_events=include_events
                )
                if entry is not None:
                    items.append(entry)
        items.sort(key=lambda entry: entry.get("started_at") or "", reverse=True)
        return items

    def _fallback_run(self, request_obj):
        execution = request_obj.metadata.get("execution") or {}
        if not execution:
            return None
        diff_text = execution.get("diff") or ""
        created_at = getattr(request_obj, "created_at", None)
        finished_at = getattr(request_obj, "updated_at", None)
        workspace_meta = request_obj.metadata.get("workspace") or {}
        execution_errors = request_obj.metadata.get("execution_errors") or []
        diff_preview = ""
        if diff_text:
            preview_lines = diff_text.splitlines()
            diff_preview = "\n".join(preview_lines[:8])
            if len(preview_lines) > 8:
                diff_preview += "\n…"
        events: list[dict[str, object]] = [
            {
                "type": "status",
                "stage": "execution",
                "message": "Run metadata generated from stored execution artifacts.",
                "request_id": str(request_obj.id),
            }
        ]
        if workspace_meta:
            workspace_message = (
                f"Workspace {workspace_meta.get('mode', 'workspace')} "
                f"at {workspace_meta.get('path', '/workspace')} "
                f"(ref={workspace_meta.get('ref', 'unknown')})"
            )
            events.append(
                {
                    "type": "status",
                    "stage": "workspace",
                    "message": workspace_message,
                    "request_id": str(request_obj.id),
                }
            )
        if execution.get("reports"):
            events.append(
                {
                    "type": "status",
                    "stage": "codex",
                    "message": "Execution reports available; see run details for full payload.",
                    "request_id": str(request_obj.id),
                }
            )
        if diff_preview:
            events.append(
                {
                    "type": "log",
                    "stage": "diff",
                    "message": diff_preview,
                    "request_id": str(request_obj.id),
                }
            )
        status_value = (
            request_obj.state.value
            if hasattr(request_obj.state, "value")
            else str(request_obj.state)
        )
        if execution_errors:
            events.append(
                {
                    "type": "error",
                    "stage": "execution",
                    "message": execution_errors[-1].get("output")
                    or execution_errors[-1].get("message")
                    or "Execution reported errors; inspect run metadata.",
                    "request_id": str(request_obj.id),
                }
            )
            events.append(
                {
                    "type": "error",
                    "stage": "failed",
                    "message": "Run finished with errors.",
                    "request_id": str(request_obj.id),
                }
            )
        else:
            events.append(
                {
                    "type": "completed",
                    "stage": "execution",
                    "message": "Run completed. Diff available below.",
                    "request_id": str(request_obj.id),
                }
            )
        return {
            "id": hashlib.sha256(
                f"{request_obj.id}:execution".encode("utf-8")
            ).hexdigest()[:16],
            "status": status_value,
            "started_at": created_at.isoformat() if created_at else None,
            "finished_at": finished_at.isoformat() if finished_at else None,
            "diff": diff_text,
            "reports": execution.get("reports") or {},
            "artifacts": execution.get("artifacts") or {},
            "events": events,
        }

    def _build_run_entry(
        self,
        request_obj,
        run: dict[str, object],
        *,
        include_events: bool,
    ) -> dict[str, object] | None:
        raw_id = run.get("id")
        if raw_id:
            run_id = str(raw_id)
        else:
            run_id = hashlib.sha256(
                f"{request_obj.id}:{run.get('started_at')}".encode("utf-8")
            ).hexdigest()[:16]
        diff_text = run.get("diff") or ""
        base: dict[str, object] = {
            "id": run_id,
            "request_id": str(request_obj.id),
            "request_title": request_obj.payload.title,
            "status": run.get("status", "unknown"),
            "started_at": run.get("started_at"),
            "finished_at": run.get("finished_at"),
            "diff_size": len(diff_text),
        }
        if not include_events:
            return base
        detail = dict(base)
        events = [dict(event) for event in (run.get("events") or [])]
        if not events and diff_text:
            events = [
                {
                    "type": "completed",
                    "stage": "execution",
                    "message": "Run completed; detailed event log unavailable.",
                    "request_id": str(request_obj.id),
                }
            ]
        for event in events:
            event.setdefault("request_id", str(request_obj.id))
            event.setdefault("run_id", run_id)
        detail["events"] = events
        detail["diff"] = diff_text
        detail["reports"] = dict(run.get("reports") or {})
        detail["artifacts"] = dict(run.get("artifacts") or {})
        error_value = run.get("error")
        if error_value:
            detail["error"] = str(error_value)
        return detail


class MergeRequestViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        merge_requests = self._collect_merge_requests(user_id=str(request.user.id))
        serializer = serializers.MergeRequestSerializer(merge_requests, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        mr_id = str(pk) if pk is not None else ""
        merge_requests = self._collect_merge_requests(user_id=str(request.user.id))
        for mr in merge_requests:
            if mr["id"] == mr_id:
                serializer = serializers.MergeRequestSerializer(mr)
                return Response(serializer.data)
        raise NotFound("Merge request not found")

    def _collect_merge_requests(self, *, user_id: str) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        for request_obj in repository.list(user_id=user_id):
            metadata_mr = request_obj.metadata.get("mr") or {}
            if not metadata_mr:
                continue
            entry = self._build_entry(request_obj, metadata_mr)
            items.append(entry)
        items.sort(key=lambda entry: entry.get("created_at") or "", reverse=True)
        return items

    def _build_entry(
        self,
        request_obj,
        metadata_mr: dict[str, object],
    ) -> dict[str, object]:
        ref_value = metadata_mr.get("ref")
        source_branch = str(metadata_mr.get("source_branch", "") or "")
        raw_identifier = ref_value or f"{request_obj.id}:{source_branch}"
        if metadata_mr.get("id"):
            mr_id = str(metadata_mr.get("id"))
        else:
            mr_id = hashlib.sha256(str(raw_identifier).encode("utf-8")).hexdigest()[:16]
        ref = str(ref_value or "")
        diff_source = metadata_mr.get("diff") or ""
        if not diff_source:
            execution_meta = request_obj.metadata.get("execution") or {}
            diff_source = execution_meta.get("diff") or ""
        if not diff_source:
            for run in request_obj.metadata.get("runs", []) or []:
                diff_text = run.get("diff")
                if diff_text:
                    diff_source = diff_text
                    break
        entry: dict[str, object] = {
            "id": mr_id,
            "ref": ref,
            "request_id": str(request_obj.id),
            "request_title": request_obj.payload.title,
            "title": metadata_mr.get("title") or request_obj.payload.title,
            "description": metadata_mr.get("description", ""),
            "target_branch": metadata_mr.get("target_branch", ""),
            "source_branch": metadata_mr.get("source_branch", ""),
            "status": metadata_mr.get("status", "OPEN"),
            "diff": diff_source or "",
            "created_at": request_obj.updated_at.isoformat(),
        }
        return entry


class PlanViewSet(viewsets.ViewSet):  # pragma: no cover - skeleton
    permission_classes = [IsAuthenticated]

    def create(self, request):
        serializer = serializers.PlanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        use_case = GeneratePlan(
            repository=repository, executor=container.resolve_executor()
        )
        try:
            plan = use_case(str(serializer.validated_data["request_id"]))
        except KeyError as exc:  # pragma: no cover - not found
            raise NotFound(str(exc)) from exc
        response = serializers.PlanSerializer(plan)
        return Response(response.data, status=status.HTTP_200_OK)


class ExecutionViewSet(viewsets.ViewSet):  # pragma: no cover - skeleton
    permission_classes = [IsAuthenticated]

    def create(self, request):
        serializer = serializers.ExecutionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        use_case = ApplyPlan(
            repository=repository,
            executor=container.resolve_executor(),
            vcs=container.vcs_providers.resolve("gitlab"),
            provisioner=container.resolve_provisioner(),
        )
        try:
            mr_ref = use_case(
                request_id=str(serializer.validated_data["request_id"]),
                repo=serializer.validated_data["repository"],
                branch=serializer.validated_data["branch"],
            )
        except KeyError as exc:  # pragma: no cover - not found
            raise NotFound(str(exc)) from exc
        return Response({"mr_ref": mr_ref}, status=status.HTTP_202_ACCEPTED)


class ApiKeyViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = serializers.ApiKeySerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get_queryset(self):
        return ApiKey.objects.filter(user=self.request.user).order_by("-created_at")

    def create(self, request, *args, **kwargs):
        serializer = serializers.ApiKeyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        api_key, raw_key = ApiKey.create_key(
            user=request.user, name=serializer.validated_data["name"]
        )
        data = serializers.ApiKeySerializer(api_key).data
        data["key"] = raw_key
        headers = {"Location": str(api_key.id)}
        return Response(data, status=status.HTTP_201_CREATED, headers=headers)

    def destroy(self, request, pk=None):
        try:
            api_key = ApiKey.objects.get(id=pk, user=request.user)
        except ApiKey.DoesNotExist:
            raise NotFound("API key not found") from None
        api_key.is_active = False
        api_key.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class RepositoryLinkViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = serializers.RepositoryLinkSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        allowed_uids = Workspace.allowed_uids_for_user(self.request.user)
        if not allowed_uids:
            return RepositoryLink.objects.none()
        workspace_uid = self.request.query_params.get("workspace_uid")
        if workspace_uid and workspace_uid not in allowed_uids:
            raise PermissionDenied("You do not have access to this workspace.")
        queryset = RepositoryLink.objects.filter(workspace__uid__in=allowed_uids)
        if workspace_uid:
            queryset = queryset.filter(workspace__uid=workspace_uid)
        return queryset.select_related("workspace").order_by("created_at")

    def perform_create(self, serializer):
        serializer.save()


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfTokenView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(status=status.HTTP_204_NO_CONTENT)


class AuthSettingsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(_auth_settings(), status=status.HTTP_200_OK)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = serializers.RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identity_provider = _identity_provider_from_request(request)
        user = serializer.save()
        access = UserAccess.for_user(user, identity_provider=identity_provider)
        auth_config = _auth_settings()
        waitlist_enforced = bool(auth_config.get("waitlist_enabled"))
        allow_all_users = bool(auth_config.get("allow_all_users"))

        if allow_all_users or not waitlist_enforced:
            if not access.is_approved:
                access.approve()
            login(request, user)
            status_code = status.HTTP_201_CREATED
        else:
            status_code = status.HTTP_202_ACCEPTED

        waitlist_email_sent = False
        if (
            waitlist_enforced
            and not access.waitlist_notified_at
            and user.email
            and access.status == AccessStatus.PENDING
        ):
            try:
                account_emails.send_waitlist_email(
                    recipient=user.email, username=user.username
                )
                access.mark_waitlist_notified()
                waitlist_email_sent = True
            except Exception:  # pragma: no cover - mail failures should not break signup
                waitlist_email_sent = False

        payload = _serialize_user(user, access=access)
        payload["auth"] = auth_config
        payload["access"]["waitlist_email_sent"] = waitlist_email_sent
        return Response(payload, status=status_code)


class EarlyAccessRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = serializers.EarlyAccessRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        user_email_sent = False
        owner_email_sent = False
        try:
            account_emails.send_early_access_confirmation(
                recipient=payload["email"],
                team_role=payload.get("team_role"),
                project_summary=payload.get("project_summary"),
            )
            user_email_sent = True
        except Exception:  # pragma: no cover - mail failures shouldn't block form
            user_email_sent = False
            logger.exception(
                "Failed to send early access confirmation email",
                extra={"email": payload.get("email")},
            )
        owner_recipient = getattr(settings, "EARLY_ACCESS_NOTIFICATION_EMAIL", "")
        if owner_recipient and user_email_sent:
            try:
                account_emails.send_early_access_owner_alert(
                    recipient=owner_recipient,
                    requester_email=payload["email"],
                    team_role=payload.get("team_role"),
                    project_summary=payload.get("project_summary"),
                )
                owner_email_sent = True
            except Exception:  # pragma: no cover - mail failures shouldn't block form
                owner_email_sent = False
                logger.exception(
                    "Failed to notify owner about early access request",
                    extra={
                        "owner_email": owner_recipient,
                        "requester_email": payload.get("email"),
                    },
                )
        detail_message = (
            "Thanks for requesting early access. We'll reach out soon."
            if user_email_sent
            else "We couldn't send the confirmation email. Please try again later."
        )
        status_code = (
            status.HTTP_201_CREATED
            if user_email_sent
            else status.HTTP_502_BAD_GATEWAY
        )
        return Response(
            {
                "detail": detail_message,
                "user_email_sent": user_email_sent,
                "owner_email_sent": owner_email_sent,
            },
            status=status_code,
        )


@method_decorator(ensure_csrf_cookie, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = serializers.LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identity_provider = _identity_provider_from_request(request)
        user = authenticate(
            request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response(
                {"detail": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED
            )
        access = UserAccess.for_user(user, identity_provider=identity_provider)
        auth_config = _auth_settings()
        waitlist_enforced = bool(auth_config.get("waitlist_enabled"))
        allow_all_users = bool(auth_config.get("allow_all_users"))

        if access.status == AccessStatus.BLOCKED:
            return Response(
                {
                    "detail": "Account is blocked. Contact an administrator.",
                    "access": _serialize_access(access),
                    "auth": auth_config,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if waitlist_enforced and not access.is_approved:
            return Response(
                {
                    "detail": "Your account is waiting for approval.",
                    "access": _serialize_access(access),
                    "auth": auth_config,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if (allow_all_users or not waitlist_enforced) and not access.is_approved:
            access.approve()

        login(request, user)
        payload = _serialize_user(user, access=access)
        payload["auth"] = auth_config
        return Response(payload, status=status.HTTP_200_OK)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        payload = _serialize_user(user)
        payload["auth"] = _auth_settings()
        return Response(payload)
