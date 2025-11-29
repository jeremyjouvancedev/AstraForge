"""REST API views for AstraForge."""

from __future__ import annotations

import hashlib
import json

from django.contrib.auth import authenticate, login, logout

from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, NotFound, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from astraforge.accounts.models import ApiKey
from astraforge.application import tasks as app_tasks
from astraforge.application.use_cases import ApplyPlan, GeneratePlan, SubmitRequest
from astraforge.bootstrap import container, repository
from astraforge.integrations.models import RepositoryLink
from astraforge.interfaces.rest import serializers
from astraforge.interfaces.rest.renderers import EventStreamRenderer
from astraforge.infrastructure.ai.deepagent_runtime import get_deep_agent
from astraforge.infrastructure.ai.serializers import jsonable_chunk, encode_sse
from astraforge.sandbox.models import SandboxSession
from django.http import StreamingHttpResponse


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
        if not RepositoryLink.objects.filter(user=request.user).exists():
            raise PermissionDenied("Link a project before submitting requests.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_obj = serializer.save()
        SubmitRequest(repository=repository)(request_obj)
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
        items = repository.list()
        serializer = self.get_serializer(items, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="execute")
    def execute(self, request, id=None):
        serializer = serializers.ExecuteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_id = str(id)
        try:
            repository.get(request_id)
        except KeyError as exc:
            raise NotFound(f"Request {request_id} not found") from exc
        app_tasks.execute_request_task.delay(
            request_id,
            serializer.validated_data.get("spec"),
        )
        return Response({"status": "queued"}, status=status.HTTP_202_ACCEPTED)

    def get_object(self):
        from django.http import Http404

        request_id = self.kwargs[self.lookup_field]
        try:
            return repository.get(str(request_id))
        except KeyError as exc:  # pragma: no cover - fallback
            raise Http404(f"Request {request_id} not found") from exc


class ChatViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = serializers.ChatSerializer

    def create(self, request, *args, **kwargs):  # pragma: no cover - stub
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_id = str(serializer.validated_data["request_id"])
        message_content = serializer.validated_data["message"]
        try:
            request_obj = repository.get(request_id)
        except KeyError as exc:
            raise NotFound(f"Request {request_id} not found") from exc
        container.resolve_run_log().publish(
            request_id,
            {
                "type": "user_message",
                "request_id": request_id,
                "message": message_content,
            },
        )
        messages = list(request_obj.metadata.get("chat_messages", []))
        messages.append(
            {
                "role": "user",
                "message": message_content,
                "created_at": timezone.now().isoformat(),
            }
        )
        request_obj.metadata["chat_messages"] = messages
        repository.save(request_obj)
        summary = message_content.strip()
        if summary:
            title_candidate = summary.split("\n", 1)[0].strip() or summary
        else:
            title_candidate = request_obj.payload.title or "Follow-up request"
        title = title_candidate if len(title_candidate) <= 72 else f"{title_candidate[:69]}..."
        implementation_steps: list[str] = [summary] if summary else [title]
        spec_payload = {
            "title": title,
            "summary": summary or title,
            "requirements": [],
            "implementation_steps": implementation_steps,
            "risks": [],
            "acceptance_criteria": [],
            "raw_prompt": summary or title,
        }
        app_tasks.execute_request_task.delay(request_id, spec_payload)
        return Response({"status": "received"}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):  # pragma: no cover - stub
        request_id = str(pk)
        app_tasks.submit_merge_request_task.delay(request_id)
        return Response({"status": "queued"}, status=status.HTTP_202_ACCEPTED)


class RunLogStreamView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [EventStreamRenderer]

    def get(self, request, pk):  # pragma: no cover - SSE placeholder
        request_id = str(pk)
        run_log = container.resolve_run_log()

        def event_stream():
            handshake = {"request_id": request_id, "type": "heartbeat", "message": "stream_ready"}
            yield "event: message\n"
            yield "data: " + json.dumps(handshake) + "\n\n"
            for event in run_log.stream(request_id):
                yield "event: message\n"
                yield "data: " + json.dumps(event) + "\n\n"

        response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


class DeepAgentConversationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # For now we align conversation IDs with sandbox session IDs
        from astraforge.sandbox.serializers import SandboxSessionCreateSerializer, SandboxSessionSerializer
        from astraforge.sandbox.services import SandboxOrchestrator, SandboxProvisionError

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
        try:
            SandboxSession.objects.get(id=conversation_id, user=request.user)
        except SandboxSession.DoesNotExist:
            raise NotFound("Sandbox session not found for this conversation")

        serializer = serializers.DeepAgentMessageRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        messages_payload = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in serializer.validated_data["messages"]
        ]
        stream = serializer.validated_data.get("stream", True)
        config = {
            "thread_id": str(conversation_id),
            "configurable": {
                "sandbox_session_id": str(conversation_id),
            },
        }
        agent = get_deep_agent()

        if not stream:
            try:
                result = agent.invoke({"messages": messages_payload}, config=config)
            except Exception as exc:  # noqa: BLE001
                raise APIException(str(exc)) from exc  # pragma: no cover - error path
            normalized = jsonable_chunk(result)
            return Response(normalized)

        def _serialize_chunk(raw: object) -> dict[str, object]:
            # Normalize deep agent state chunk into { "messages": [{role, content}, ...] }
            normalized = jsonable_chunk(raw)
            messages = []
            if isinstance(normalized, dict):
                messages = normalized.get("messages", []) or []

            json_messages: list[dict[str, str]] = []
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                role_value = msg.get("type") or msg.get("role") or "assistant"
                role = str(role_value).lower()
                # Skip human/user echoes; the frontend already renders user messages
                if role in {"human", "user"}:
                    continue
                if role in {"ai", "assistant", "model"}:
                    norm_role = "assistant"
                elif role in {"system"}:
                    norm_role = "system"
                else:
                    norm_role = role or "assistant"

                content = msg.get("data", {}).get("content")
                if isinstance(content, list):
                    parts: list[str] = []
                    for part in content:
                        if isinstance(part, dict) and isinstance(part.get("text"), str):
                            parts.append(part["text"])
                    content_text = "\n".join(parts)
                else:
                    content_text = "" if content is None else str(content)
                if not content_text.strip():
                    continue
                json_messages.append(
                    {
                        "role": norm_role,
                        "content": content_text,
                    }
                )
            if json_messages:
                return {"messages": json_messages}
            return {"raw": str(raw)}

        def event_stream():
            try:
                for chunk in agent.stream(
                    {"messages": messages_payload},
                    config=config,
                    stream_mode="values",
                ):
                    payload = _serialize_chunk(chunk)
                    yield encode_sse(payload)
            except Exception as exc:  # noqa: BLE001
                error_payload = {"error": str(exc)}
                yield encode_sse(error_payload)

        response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


class RunViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        runs = self._collect_runs(include_events=False)
        serializer = serializers.RunSummarySerializer(runs, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        run_id = str(pk) if pk is not None else ""
        runs = self._collect_runs(include_events=True)
        for run in runs:
            if run["id"] == run_id:
                serializer = serializers.RunDetailSerializer(run)
                return Response(serializer.data)
        raise NotFound("Run not found")

    def _collect_runs(self, *, include_events: bool) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        for request_obj in repository.list():
            runs_meta = list(request_obj.metadata.get("runs", []) or [])
            if not runs_meta:
                fallback = self._fallback_run(request_obj)
                if fallback is not None:
                    runs_meta = [fallback]
            for run in runs_meta:
                entry = self._build_run_entry(request_obj, run, include_events=include_events)
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
            request_obj.state.value if hasattr(request_obj.state, "value") else str(request_obj.state)
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
            "id": hashlib.sha256(f"{request_obj.id}:execution".encode("utf-8")).hexdigest()[:16],
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
        merge_requests = self._collect_merge_requests()
        serializer = serializers.MergeRequestSerializer(merge_requests, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        mr_id = str(pk) if pk is not None else ""
        merge_requests = self._collect_merge_requests()
        for mr in merge_requests:
            if mr["id"] == mr_id:
                serializer = serializers.MergeRequestSerializer(mr)
                return Response(serializer.data)
        raise NotFound("Merge request not found")

    def _collect_merge_requests(self) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        for request_obj in repository.list():
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
        return RepositoryLink.objects.filter(user=self.request.user).order_by("created_at")

    def perform_create(self, serializer):
        serializer.save()


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfTokenView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = serializers.RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        login(request, user)
        return Response(
            {"username": user.username, "email": user.email},
            status=status.HTTP_201_CREATED,
        )


@method_decorator(ensure_csrf_cookie, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = serializers.LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response(
                {"detail": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED
            )
        login(request, user)
        return Response(
            {"username": user.username, "email": user.email}, status=status.HTTP_200_OK
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({"username": user.username, "email": user.email})
