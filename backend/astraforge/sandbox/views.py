from __future__ import annotations

import base64
import shlex
import time

from django.http import HttpResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from astraforge.sandbox.models import SandboxSession
from astraforge.sandbox.serializers import (
    SandboxArtifactSerializer,
    SandboxExecSerializer,
    SandboxFileExportSerializer,
    SandboxSessionCreateSerializer,
    SandboxSessionSerializer,
    SandboxSnapshotCreateSerializer,
    SandboxSnapshotSerializer,
    SandboxUploadSerializer,
)
from astraforge.sandbox.services import SandboxOrchestrator, SandboxProvisionError


# 1x1 transparent PNG placeholder to avoid broken images until
# real screenshot capture is wired to the sandbox daemon.
_PLACEHOLDER_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
)


class SandboxSessionViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    serializer_class = SandboxSessionSerializer
    orchestrator = SandboxOrchestrator()

    def get_queryset(self):
        return SandboxSession.objects.filter(user=self.request.user).order_by("-created_at")

    def create(self, request, *args, **kwargs):
        create_serializer = SandboxSessionCreateSerializer(data=request.data, context={"request": request})
        create_serializer.is_valid(raise_exception=True)
        session = create_serializer.save()
        try:
            self.orchestrator.provision(session)
        except SandboxProvisionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        output = SandboxSessionSerializer(session)
        headers = {"Location": str(session.id)}
        return Response(output.data, status=status.HTTP_201_CREATED, headers=headers)

    def destroy(self, request, *args, **kwargs):
        session = self.get_object()
        self.orchestrator.terminate(session)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="stop")
    def stop(self, request, pk=None):
        return self.destroy(request, pk=pk)

    @action(detail=True, methods=["post"], url_path="exec")
    def exec(self, request, pk=None):  # noqa: A003
        return self.shell(request, pk=pk)

    @action(detail=True, methods=["post"], url_path="shell")
    def shell(self, request, pk=None):
        session = self.get_object()
        serializer = SandboxExecSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        start = time.monotonic()
        try:
            result = self.orchestrator.execute(
                session,
                serializer.get_command(),
                cwd=serializer.validated_data.get("cwd") or None,
                timeout_sec=serializer.validated_data.get("timeout_sec"),
            )
        except SandboxProvisionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        duration = time.monotonic() - start
        capture_stdout = serializer.validated_data.get("capture_stdout", True)
        capture_stderr = serializer.validated_data.get("capture_stderr", True)
        return Response(
            {
                "exit_code": result.exit_code,
                "stdout": result.stdout if capture_stdout else "",
                "stderr": result.stderr if capture_stderr else "",
                "duration_sec": round(duration, 3),
            }
        )

    @action(detail=True, methods=["post"], url_path="upload")
    def upload(self, request, pk=None):
        session = self.get_object()
        serializer = SandboxUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = self.orchestrator.upload(
                session,
                serializer.validated_data["path"],
                serializer.get_bytes(),
            )
        except SandboxProvisionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="files/upload")
    def files_upload(self, request, pk=None):
        session = self.get_object()
        path = request.query_params.get("path") or request.data.get("path")
        if not path:
            return Response({"detail": "path is required"}, status=status.HTTP_400_BAD_REQUEST)
        content = request.body or b""
        try:
            result = self.orchestrator.upload_bytes(session, path, content)
        except SandboxProvisionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"exit_code": result.exit_code, "stdout": result.stdout, "stderr": result.stderr},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="files/export")
    def files_export(self, request, pk=None):
        session = self.get_object()
        serializer = SandboxFileExportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        filename = serializer.validated_data.get("filename") or serializer.validated_data["path"].split("/")[-1]
        try:
            artifact = self.orchestrator.export_file(
                session,
                path=serializer.validated_data["path"],
                filename=filename,
                content_type=serializer.validated_data.get("content_type") or "",
            )
        except SandboxProvisionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(SandboxArtifactSerializer(artifact).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="files/content")
    def files_content(self, request, pk=None):
        """Stream a file's bytes from inside the sandbox as a direct download."""
        session = self.get_object()
        path = request.query_params.get("path")
        if not path:
            return Response({"detail": "path is required"}, status=status.HTTP_400_BAD_REQUEST)
        filename = request.query_params.get("filename") or path.rsplit("/", 1)[-1] or "download"
        base64_cmd = f"base64 < {shlex.quote(path)}"
        try:
            result = self.orchestrator.execute(session, base64_cmd)
        except SandboxProvisionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if result.exit_code != 0:
            message = (result.stdout or result.stderr or "").strip() or "Failed to read file"
            return Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)
        raw_b64 = (result.stdout or "").strip()
        try:
            content = base64.b64decode(raw_b64.encode("ascii")) if raw_b64 else b""
        except Exception:
            content = b""
        response = HttpResponse(content, content_type="application/octet-stream")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    @action(detail=True, methods=["post"], url_path="snapshot")
    def snapshot(self, request, pk=None):
        session = self.get_object()
        serializer = SandboxSnapshotCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            snapshot = self.orchestrator.create_snapshot(
                session,
                label=serializer.validated_data.get("label", ""),
                include_paths=serializer.validated_data.get("include_paths"),
                exclude_paths=serializer.validated_data.get("exclude_paths"),
            )
        except SandboxProvisionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(SandboxSnapshotSerializer(snapshot).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="artifacts")
    def artifacts(self, request, pk=None):
        session = self.get_object()
        artifacts = self.orchestrator.list_artifacts(session)
        serializer = SandboxArtifactSerializer(artifacts, many=True)
        return Response({"session_id": str(session.id), "artifacts": serializer.data})

    @action(detail=True, methods=["get", "post"], url_path="snapshots")
    def snapshots(self, request, pk=None):
        session = self.get_object()
        if request.method.lower() == "get":
            snapshots = self.orchestrator.list_snapshots(session)
            data = SandboxSnapshotSerializer(snapshots, many=True).data
            return Response({"session_id": str(session.id), "snapshots": data})

        serializer = SandboxSnapshotCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            snapshot = self.orchestrator.create_snapshot(
                session,
                label=serializer.validated_data.get("label", ""),
                include_paths=serializer.validated_data.get("include_paths"),
                exclude_paths=serializer.validated_data.get("exclude_paths"),
            )
        except SandboxProvisionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        output = SandboxSnapshotSerializer(snapshot)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="heartbeat")
    def heartbeat(self, request, pk=None):
        session = self.get_object()
        session.mark_heartbeat()
        return Response({"status": session.status, "last_heartbeat_at": session.last_heartbeat_at})

    @action(detail=True, methods=["post"], url_path="input/mouse")
    def input_mouse(self, request, pk=None):
        return Response(
            {"detail": "Mouse input not yet implemented in the sandbox daemon"},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )

    @action(detail=True, methods=["post"], url_path="input/keyboard")
    def input_keyboard(self, request, pk=None):
        return Response(
            {"detail": "Keyboard input not yet implemented in the sandbox daemon"},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )

    @action(detail=True, methods=["get"], url_path="screenshot")
    def screenshot(self, request, pk=None):
        session = self.get_object()
        try:
            image_bytes = self.orchestrator.capture_screenshot(session)
        except SandboxProvisionError:
            # Fall back to a transparent 1x1 PNG so the frontend does not show a broken image.
            return HttpResponse(_PLACEHOLDER_PNG, content_type="image/png")
        return HttpResponse(image_bytes, content_type="image/png")

    @action(detail=True, methods=["get"], url_path="stream/view")
    def stream_view(self, request, pk=None):
        return Response(
            {"detail": "Live view streaming requires sandbox daemon integration"},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )
