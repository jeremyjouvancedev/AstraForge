"""REST API views for AstraForge."""

from __future__ import annotations

import hashlib
import json
import re

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
from langchain_core.messages import message_to_dict


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
        title = (
            title_candidate
            if len(title_candidate) <= 72
            else f"{title_candidate[:69]}..."
        )
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
        path_pattern = re.compile(rf"({re.escape(workspace_root)}/[^\s'\"`]+)")
        sandbox_link_pattern = re.compile(
            r"\[(?P<label>[^\]]+)\]\(sandbox:(?P<path>[^\)]+)\)"
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
                    f"/api/sandbox/sessions/{session.id}/files/content"
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

        def export_artifacts_from_text(text: str | None) -> list[dict[str, object]]:
            if not text or workspace_root not in text:
                return []
            matches = path_pattern.findall(text)
            if not matches:
                return []
            artifacts: list[dict[str, object]] = []
            for path in matches:
                artifact_dict = _export_path(path)
                if artifact_dict is not None:
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
                content_text = rewrite_sandbox_links(_content_to_text(content))
                artifacts_from_data = data.get("artifacts")
                auto_artifacts = export_artifacts_from_text(content_text)
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

                        artifacts = result.get("artifacts")
                        if isinstance(artifacts, list):
                            for artifact in artifacts:
                                tool_artifact_payload = {
                                    "event": "tool_artifact",
                                    "data": {
                                        "tool_call_id": result.get("tool_call_id"),
                                        "tool_name": result.get("tool_name"),
                                        "artifact": artifact,
                                    },
                                }
                                yield encode_sse(tool_artifact_payload)

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
        return RepositoryLink.objects.filter(user=self.request.user).order_by(
            "created_at"
        )

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
