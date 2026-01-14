from __future__ import annotations

import base64
import binascii
import os
from typing import Any

from rest_framework import serializers

from astraforge.accounts.models import Workspace
from astraforge.quotas.services import QuotaExceeded, get_quota_service
from astraforge.sandbox.models import SandboxArtifact, SandboxSession, SandboxSnapshot


def _default_image() -> str:
    return os.getenv("SANDBOX_IMAGE") or os.getenv("CODEX_WORKSPACE_IMAGE") or "astraforge/codex-cli:latest"


class SandboxSessionCreateSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False, allow_null=True)
    mode = serializers.ChoiceField(choices=SandboxSession.Mode.choices, default=SandboxSession.Mode.DOCKER)
    image = serializers.CharField(default=_default_image)
    cpu = serializers.CharField(required=False, allow_blank=True)
    memory = serializers.CharField(required=False, allow_blank=True)
    ephemeral_storage = serializers.CharField(required=False, allow_blank=True)
    restore_snapshot_id = serializers.UUIDField(required=False, allow_null=True)
    idle_timeout_sec = serializers.IntegerField(default=300, min_value=60)
    max_lifetime_sec = serializers.IntegerField(default=3600, min_value=300)
    workspace_uid = serializers.CharField(required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False, default=dict)

    def validate(self, attrs):
        idle = attrs.get("idle_timeout_sec")
        max_lifetime = attrs.get("max_lifetime_sec")
        if idle and max_lifetime and idle > max_lifetime:
            raise serializers.ValidationError("idle_timeout_sec cannot exceed max_lifetime_sec")
        return attrs

    def create(self, validated_data):  # pragma: no cover - used by viewset
        user = self.context["request"].user
        session_id = validated_data.pop("id", None)
        workspace_uid = validated_data.pop("workspace_uid", None)
        try:
            workspace = Workspace.resolve_for_user(user, preferred_uid=workspace_uid)
        except PermissionError as exc:
            raise serializers.ValidationError({"workspace_uid": [str(exc)]}) from exc
        quota_service = get_quota_service()
        try:
            quota_service.register_sandbox_session(workspace)
        except QuotaExceeded as exc:
            raise serializers.ValidationError({"workspace_uid": [str(exc)]}) from exc
        return SandboxSession.objects.create(
            user=user,
            workspace=workspace,
            id=session_id,
            **validated_data,
        )


class SandboxSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = SandboxSnapshot
        fields = [
            "id",
            "label",
            "s3_key",
            "archive_path",
            "size_bytes",
            "include_paths",
            "exclude_paths",
            "created_at",
        ]
        read_only_fields = fields


class SandboxArtifactSerializer(serializers.ModelSerializer):
    class Meta:
        model = SandboxArtifact
        fields = [
            "id",
            "filename",
            "content_type",
            "size_bytes",
            "storage_path",
            "download_url",
            "created_at",
        ]
        read_only_fields = fields


class SandboxSessionSerializer(serializers.ModelSerializer):
    snapshot_ids = serializers.SerializerMethodField()
    artifacts_count = serializers.SerializerMethodField()
    workspace_uid = serializers.SerializerMethodField()
    workspace_name = serializers.SerializerMethodField()

    class Meta:
        model = SandboxSession
        fields = [
            "id",
            "mode",
            "image",
            "cpu",
            "memory",
            "ephemeral_storage",
            "restore_snapshot_id",
            "status",
            "ref",
            "control_endpoint",
            "workspace_path",
            "artifact_base_url",
            "workspace_uid",
            "workspace_name",
            "idle_timeout_sec",
            "max_lifetime_sec",
            "last_activity_at",
            "last_heartbeat_at",
            "expires_at",
            "error_message",
            "metadata",
            "cpu_seconds",
            "storage_bytes",
            "snapshot_ids",
            "artifacts_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "ref",
            "control_endpoint",
            "workspace_path",
            "artifact_base_url",
            "workspace_uid",
            "workspace_name",
            "last_activity_at",
            "last_heartbeat_at",
            "expires_at",
            "error_message",
            "metadata",
            "cpu_seconds",
            "storage_bytes",
            "snapshot_ids",
            "artifacts_count",
            "created_at",
            "updated_at",
        ]

    def get_snapshot_ids(self, obj: SandboxSession) -> list[str]:
        return [str(snapshot.id) for snapshot in obj.snapshots.all()]

    def get_artifacts_count(self, obj: SandboxSession) -> int:
        return obj.artifacts.count()

    def get_workspace_uid(self, obj: SandboxSession) -> str | None:
        return obj.workspace.uid if obj.workspace else None

    def get_workspace_name(self, obj: SandboxSession) -> str | None:
        return obj.workspace.name if obj.workspace else None


class SandboxExecSerializer(serializers.Serializer):
    command = serializers.JSONField()
    cwd = serializers.CharField(required=False, allow_blank=True)
    timeout_sec = serializers.IntegerField(required=False, min_value=1)
    capture_stdout = serializers.BooleanField(required=False, default=True)
    capture_stderr = serializers.BooleanField(required=False, default=True)

    def validate_command(self, value: Any) -> Any:
        if isinstance(value, str):
            return value
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return value
        raise serializers.ValidationError("Must be a string or list of strings")

    def get_command(self) -> Any:
        return self.validated_data["command"]


class SandboxUploadSerializer(serializers.Serializer):
    path = serializers.CharField()
    content = serializers.CharField(help_text="File contents. Base64 allowed when encoding=base64")
    encoding = serializers.ChoiceField(choices=["utf-8", "base64"], default="utf-8")

    def get_bytes(self) -> bytes:
        content = self.validated_data["content"]
        if self.validated_data.get("encoding") == "base64":
            try:
                return base64.b64decode(content)
            except (binascii.Error, ValueError) as exc:
                raise serializers.ValidationError("Invalid base64 content") from exc
        return content.encode("utf-8")


class SandboxFileExportSerializer(serializers.Serializer):
    path = serializers.CharField()
    filename = serializers.CharField(required=False, allow_blank=True)
    content_type = serializers.CharField(required=False, allow_blank=True)


class SandboxSnapshotCreateSerializer(serializers.Serializer):
    label = serializers.CharField(required=False, allow_blank=True)
    include_paths = serializers.ListField(
        child=serializers.CharField(), required=False, allow_empty=True
    )
    exclude_paths = serializers.ListField(
        child=serializers.CharField(), required=False, allow_empty=True
    )
