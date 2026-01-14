"""Serializers bridging HTTP payloads and domain objects."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from astraforge.accounts.models import ApiKey, Workspace, WorkspaceRole
from astraforge.integrations.models import RepositoryLink
from astraforge.domain.models.request import Attachment, Request, RequestPayload
from astraforge.quotas.services import QuotaExceeded, get_quota_service


class RequestSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    tenant_id = serializers.CharField(required=False, allow_blank=True, default="")
    source = serializers.CharField(default="direct_user")
    sender = serializers.EmailField(required=False, allow_blank=True)
    project_id = serializers.UUIDField()
    prompt = serializers.CharField(trim_whitespace=False)
    llm_provider = serializers.ChoiceField(
        choices=["openai", "ollama"],
        required=False,
        allow_null=True,
    )
    llm_model = serializers.CharField(required=False, allow_blank=True)
    reasoning_effort = serializers.ChoiceField(
        choices=["low", "medium", "high"],
        default="high",
        required=False,
    )
    reasoning_check = serializers.BooleanField(required=False, allow_null=True)
    attachments = serializers.ListField(
        child=serializers.JSONField(),
        required=False,
        default=list,
    )

    def create(self, validated_data):
        raw_prompt = validated_data.pop("prompt")
        project_id = validated_data.pop("project_id")
        llm_provider = (validated_data.pop("llm_provider", None) or "").strip().lower()
        llm_model = (validated_data.pop("llm_model", None) or "").strip()
        reasoning_effort = validated_data.pop("reasoning_effort", "high")
        reasoning_check = validated_data.pop("reasoning_check", None)
        raw_attachments = validated_data.pop("attachments", [])
        request_obj = self.context.get("request")
        if request_obj is None or request_obj.user.is_anonymous:
            raise serializers.ValidationError(
                {"project_id": ["Authentication required to select a project."]}
            )
        user_id = str(request_obj.user.id)
        try:
            workspace = Workspace.resolve_for_user(
                request_obj.user,
                preferred_uid=validated_data.pop("tenant_id", None),
            )
        except PermissionError as exc:
            raise serializers.ValidationError({"tenant_id": [str(exc)]}) from exc
        try:
            repository_link = RepositoryLink.objects.get(
                id=project_id, workspace=workspace
            )
        except RepositoryLink.DoesNotExist as exc:
            raise serializers.ValidationError(
                {"project_id": ["Select a project linked to this workspace."]}
            ) from exc

        quota_service = get_quota_service()
        try:
            quota_service.register_request_submission(workspace)
        except QuotaExceeded as exc:
            raise serializers.ValidationError(
                {"tenant_id": [str(exc)]}
            ) from exc

        attachments = [
            Attachment(
                uri=att.get("uri", ""),
                name=att.get("name", ""),
                content_type=att.get("content_type", ""),
            )
            for att in raw_attachments
        ]

        payload = RequestPayload(
            title=self._derive_title(raw_prompt),
            description=raw_prompt,
            context={},
            attachments=attachments,
        )
        request_id = str(validated_data.get("id") or "")
        if not request_id:
            import uuid

            request_id = str(uuid.uuid4())
        validated_data["id"] = request_id
        validated_data.setdefault("sender", "")
        validated_data["tenant_id"] = workspace.uid
        metadata = {
            "project": {
                "id": str(repository_link.id),
                "provider": repository_link.provider,
                "repository": repository_link.repository,
                "base_url": repository_link.effective_base_url(),
                "access_token": repository_link.access_token,
            },
            "workspace": {"uid": workspace.uid, "name": workspace.name},
        }
        llm_config: dict[str, str | bool] = {}
        if llm_provider:
            llm_config["provider"] = llm_provider
        if llm_model:
            llm_config["model"] = llm_model
        if reasoning_effort:
            llm_config["reasoning_effort"] = reasoning_effort
        if reasoning_check is not None:
            llm_config["reasoning_check"] = reasoning_check
        if llm_config:
            metadata["llm"] = llm_config
        metadata["prompt"] = raw_prompt
        initial_message = {
            "role": "user",
            "message": raw_prompt,
            "created_at": timezone.now().isoformat(),
        }
        if raw_attachments:
            initial_message["attachments"] = raw_attachments
        metadata["chat_messages"] = [initial_message]
        return Request(
            payload=payload,
            metadata=metadata,
            user_id=user_id,
            **validated_data,
        )

    def to_representation(self, instance: Request):
        project_internal = instance.metadata.get("project", {}) or {}
        project_public = dict(project_internal)
        project_public.pop("access_token", None)
        metadata_public = dict(instance.metadata)
        metadata_public = self._append_run_assistant_messages(metadata_public)
        project_meta = metadata_public.get("project")
        if isinstance(project_meta, dict):
            metadata_public = dict(metadata_public)
            sanitized_project = dict(project_meta)
            sanitized_project.pop("access_token", None)
            metadata_public["project"] = sanitized_project
        return {
            "id": instance.id,
            "tenant_id": instance.tenant_id,
            "source": instance.source,
            "sender": instance.sender,
            "project": project_public,
            "state": instance.state.value,
            "payload": {
                "title": instance.payload.title,
                "description": instance.payload.description,
                "context": instance.payload.context,
                "attachments": [
                    {
                        "uri": att.uri,
                        "name": att.name,
                        "content_type": att.content_type,
                    }
                    for att in instance.payload.attachments
                ],
            },
            "artifacts": instance.artifacts,
            "metadata": metadata_public,
        }

    @staticmethod
    def _derive_title(prompt: str) -> str:
        candidate = ""
        if prompt:
            first_line = prompt.split("\n", 1)[0].strip()
            candidate = first_line if len(first_line) >= 12 else prompt.strip()
        candidate = candidate or "User request"
        limit = 72
        return candidate if len(candidate) <= limit else f"{candidate[: limit - 3]}..."

    def _append_run_assistant_messages(self, metadata: dict[str, object]) -> dict[str, object]:
        runs = metadata.get("runs")
        if not isinstance(runs, list):
            return metadata
        existing_messages = metadata.get("chat_messages")
        base_messages = list(existing_messages) if isinstance(existing_messages, list) else []
        seen_signatures: set[tuple[str, str]] = set()
        for entry in base_messages:
            if not isinstance(entry, dict):
                continue
            role = str(entry.get("role", "")).lower()
            content = (
                str(entry.get("message", "")).strip()
                or str(entry.get("content", "")).strip()
            )
            if role and content:
                seen_signatures.add((role, content))
        additions: list[dict[str, object]] = []
        for run in runs:
            if not isinstance(run, dict):
                continue
            artifacts = run.get("artifacts")
            if not isinstance(artifacts, dict):
                continue
            final_message = artifacts.get("final_message")
            if not isinstance(final_message, str):
                continue
            content = final_message.strip()
            if not content:
                continue
            signature = ("assistant", content)
            if signature in seen_signatures:
                continue
            created_at = (
                run.get("finished_at")
                or run.get("started_at")
                or timezone.now().isoformat()
            )
            additions.append(
                {
                    "role": "assistant",
                    "message": content,
                    "created_at": created_at,
                    "run_id": run.get("id"),
                }
            )
            seen_signatures.add(signature)
        if not additions:
            return metadata
        merged = base_messages + additions
        updated = dict(metadata)
        updated["chat_messages"] = merged
        return updated


class WorkspaceSerializer(serializers.Serializer):
    uid = serializers.SlugField(read_only=True)
    name = serializers.CharField()
    role = serializers.ChoiceField(choices=WorkspaceRole.choices, required=False)
    plan = serializers.CharField(read_only=True)

    def create(self, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return Workspace.create_for_user(name=validated_data["name"], user=user)

    def to_representation(self, instance: Workspace):
        role = (
            instance.members.filter(user=getattr(self.context.get("request"), "user", None))
            .values_list("role", flat=True)
            .first()
        )
        return {
            "uid": instance.uid,
            "name": instance.name,
            "role": role or WorkspaceRole.MEMBER,
            "plan": instance.plan,
        }


class ChatSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    message = serializers.CharField(trim_whitespace=False)
    attachments = serializers.ListField(
        child=serializers.JSONField(),
        required=False,
        default=list,
    )


class PlanRequestSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()


class PlanStepSerializer(serializers.Serializer):
    description = serializers.CharField()
    completed = serializers.BooleanField()
    risk = serializers.CharField(allow_null=True, required=False)


class PlanSerializer(serializers.Serializer):
    steps = PlanStepSerializer(many=True)
    summary = serializers.CharField()


class ExecutionRequestSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    repository = serializers.CharField()
    branch = serializers.CharField()


class DeepAgentChatMessageSerializer(serializers.Serializer):
    role = serializers.ChoiceField(
        choices=["user", "assistant", "system", "tool"], default="user"
    )
    content = serializers.CharField()


class DeepAgentMessageRequestSerializer(serializers.Serializer):
    messages = serializers.ListField(
        child=DeepAgentChatMessageSerializer(), allow_empty=False
    )
    stream = serializers.BooleanField(default=True)
    llm_provider = serializers.ChoiceField(
        choices=["openai", "ollama"],
        required=False,
        allow_null=True,
    )
    llm_model = serializers.CharField(required=False, allow_blank=True)
    reasoning_effort = serializers.ChoiceField(
        choices=["low", "medium", "high"],
        default="high",
        required=False,
    )
    reasoning_check = serializers.BooleanField(required=False, allow_null=True)


class ExecuteRequestSerializer(serializers.Serializer):
    llm_provider = serializers.ChoiceField(
        choices=["openai", "ollama"],
        required=False,
        allow_null=True,
    )
    llm_model = serializers.CharField(required=False, allow_blank=True)
    reasoning_effort = serializers.ChoiceField(
        choices=["low", "medium", "high"],
        default="high",
        required=False,
    )
    reasoning_check = serializers.BooleanField(required=False, allow_null=True)


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_username(self, value: str) -> str:
        user_model = get_user_model()
        if user_model.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already exists")
        return value

    def create(self, validated_data):
        user_model = get_user_model()
        return user_model.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class EarlyAccessRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    team_role = serializers.CharField(required=False, allow_blank=True, max_length=160)
    project_summary = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=2000,
        help_text="What the requester is building and why they need AstraForge.",
    )


class ApiKeySerializer(serializers.ModelSerializer):
    key = serializers.CharField(
        read_only=True, help_text="Plaintext API key. Shown only once."
    )

    class Meta:
        model = ApiKey
        fields = ["id", "name", "created_at", "last_used_at", "is_active", "key"]
        read_only_fields = ["id", "created_at", "last_used_at", "is_active", "key"]


class ApiKeyCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)


class RepositoryLinkSerializer(serializers.ModelSerializer):
    access_token = serializers.CharField(write_only=True, trim_whitespace=False)
    workspace_uid = serializers.SlugField(write_only=True)
    workspace = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = RepositoryLink
        fields = [
            "id",
            "provider",
            "repository",
            "base_url",
            "access_token",
            "workspace",
            "workspace_uid",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "workspace",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        provider = attrs.get("provider")
        base_url = attrs.get("base_url") or ""
        if provider == RepositoryLink.Provider.GITLAB:
            attrs["base_url"] = (
                base_url or RepositoryLink.DEFAULT_GITLAB_URL
            )
        elif base_url:
            raise serializers.ValidationError(
                {"base_url": "Only GitLab links support custom base URLs."}
            )
        workspace_uid_raw = attrs.get("workspace_uid") or (
            self.initial_data.get("workspace_uid")
            if isinstance(self.initial_data, dict)
            else None
        )
        workspace_uid = str(workspace_uid_raw or "").strip()
        request = self.context.get("request")
        if request is None or request.user.is_anonymous:
            raise serializers.ValidationError(
                {"workspace_uid": "Authentication required to link a repository."}
            )
        allowed = Workspace.allowed_uids_for_user(request.user)
        if workspace_uid in {"", "tenant-default"}:
            workspace_uid = next(iter(allowed), "")
        if not workspace_uid:
            raise serializers.ValidationError(
                {"workspace_uid": "Workspace is required."}
            )
        if workspace_uid not in allowed:
            raise serializers.ValidationError(
                {"workspace_uid": "You do not have access to this workspace."}
            )
        attrs["workspace_uid"] = workspace_uid
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        workspace_uid = validated_data.pop("workspace_uid")
        try:
            workspace = Workspace.objects.get(uid=workspace_uid)
        except Workspace.DoesNotExist as exc:  # pragma: no cover - defensive
            raise serializers.ValidationError(
                {"workspace_uid": "Workspace not found."}
            ) from exc
        return RepositoryLink.objects.create(
            user=request.user,
            workspace=workspace,
            **validated_data,
        )

    def get_workspace(self, obj: RepositoryLink) -> dict[str, str] | None:
        if not obj.workspace_id:
            return None
        return {"uid": obj.workspace.uid, "name": obj.workspace.name}


class RunSummarySerializer(serializers.Serializer):
    id = serializers.CharField()
    request_id = serializers.CharField()
    request_title = serializers.CharField()
    status = serializers.CharField()
    started_at = serializers.CharField(allow_null=True)
    finished_at = serializers.CharField(allow_null=True)
    diff_size = serializers.IntegerField()


class RunDetailSerializer(RunSummarySerializer):
    events = serializers.ListField(
        child=serializers.JSONField(),
        allow_empty=True,
    )
    diff = serializers.CharField(allow_blank=True, required=False)
    reports = serializers.JSONField(required=False)
    artifacts = serializers.JSONField(required=False)
    error = serializers.CharField(allow_blank=True, required=False)


class MergeRequestSerializer(serializers.Serializer):
    id = serializers.CharField()
    request_id = serializers.CharField()
    request_title = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    target_branch = serializers.CharField(allow_blank=True, required=False)
    source_branch = serializers.CharField(allow_blank=True, required=False)
    status = serializers.CharField()
    ref = serializers.CharField()
    diff = serializers.CharField(allow_blank=True, required=False)
    created_at = serializers.CharField()


class ActivityConsumptionSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["request", "sandbox"])
    ordinal = serializers.IntegerField(required=False, allow_null=True)
    cpu_seconds = serializers.FloatField(required=False, allow_null=True)
    storage_bytes = serializers.IntegerField(required=False, allow_null=True)


class ActivityEventSerializer(serializers.Serializer):
    id = serializers.CharField()
    type = serializers.ChoiceField(choices=["Request", "Run", "Merge", "Sandbox"])
    title = serializers.CharField()
    description = serializers.CharField()
    timestamp = serializers.CharField()
    href = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    consumption = ActivityConsumptionSerializer(required=False, allow_null=True)


class ComputerUseRunCreateSerializer(serializers.Serializer):
    goal = serializers.CharField()
    sandbox_session_id = serializers.UUIDField(required=False, allow_null=True)
    sandbox = serializers.JSONField(required=False, default=dict)
    decision_provider = serializers.CharField(required=False, allow_blank=True)
    decision_script = serializers.ListField(
        child=serializers.JSONField(), required=False, allow_empty=True
    )
    config = serializers.JSONField(required=False, default=dict)


class ComputerUseRunSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    goal = serializers.CharField()
    final_response = serializers.CharField(allow_blank=True, required=False)
    status = serializers.CharField()
    stop_reason = serializers.CharField(allow_blank=True, required=False)
    trace_dir = serializers.CharField(allow_blank=True, required=False)
    sandbox_session_id = serializers.UUIDField(required=False, allow_null=True)
    pending_checks = serializers.ListField(child=serializers.JSONField(), required=False)
    step_index = serializers.IntegerField(required=False)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class ComputerUseRunAckSerializer(serializers.Serializer):
    acknowledged = serializers.ListField(child=serializers.CharField(), allow_empty=True)
    decision = serializers.ChoiceField(choices=["approve", "deny"])
