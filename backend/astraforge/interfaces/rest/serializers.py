"""Serializers bridging HTTP payloads and domain objects."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import serializers

from astraforge.accounts.models import ApiKey
from astraforge.integrations.models import RepositoryLink
from astraforge.domain.models.request import Attachment, Request, RequestPayload


class AttachmentSerializer(serializers.Serializer):
    uri = serializers.CharField()
    name = serializers.CharField()
    content_type = serializers.CharField()


class RequestPayloadSerializer(serializers.Serializer):
    title = serializers.CharField()
    description = serializers.CharField()
    context = serializers.JSONField(required=False)
    attachments = AttachmentSerializer(many=True, required=False)


class RequestSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    tenant_id = serializers.CharField(default="tenant-default")
    source = serializers.CharField(default="direct_user")
    sender = serializers.EmailField(required=False, allow_blank=True)
    project_id = serializers.UUIDField()
    payload = RequestPayloadSerializer()

    def create(self, validated_data):
        payload_data = validated_data.pop("payload")
        project_id = validated_data.pop("project_id")
        request_obj = self.context.get("request")
        if request_obj is None or request_obj.user.is_anonymous:
            raise serializers.ValidationError(
                {"project_id": "Authentication required to select a project."}
            )
        try:
            repository_link = RepositoryLink.objects.get(
                id=project_id, user=request_obj.user
            )
        except RepositoryLink.DoesNotExist as exc:
            raise serializers.ValidationError(
                {"project_id": "Select a project linked to your account."}
            ) from exc
        attachments = [Attachment(**att) for att in payload_data.get("attachments", [])]
        payload = RequestPayload(
            title=payload_data["title"],
            description=payload_data["description"],
            context=payload_data.get("context", {}),
            attachments=attachments,
        )
        request_id = str(validated_data.get("id") or "")
        if not request_id:
            import uuid

            request_id = str(uuid.uuid4())
        validated_data["id"] = request_id
        validated_data.setdefault("sender", "")
        metadata = {
            "project": {
                "id": str(repository_link.id),
                "provider": repository_link.provider,
                "repository": repository_link.repository,
                "base_url": repository_link.effective_base_url(),
                "access_token": repository_link.access_token,
            }
        }
        return Request(payload=payload, metadata=metadata, **validated_data)

    def to_representation(self, instance: Request):
        project_internal = instance.metadata.get("project", {}) or {}
        project_public = dict(project_internal)
        project_public.pop("access_token", None)
        metadata_public = dict(instance.metadata)
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


class ChatSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    message = serializers.CharField()


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


class DevelopmentSpecSerializer(serializers.Serializer):
    title = serializers.CharField()
    summary = serializers.CharField()
    requirements = serializers.ListField(
        child=serializers.CharField(), allow_empty=True, required=False
    )
    implementation_steps = serializers.ListField(
        child=serializers.CharField(), allow_empty=True, required=False
    )
    risks = serializers.ListField(
        child=serializers.CharField(), allow_empty=True, required=False
    )
    acceptance_criteria = serializers.ListField(
        child=serializers.CharField(), allow_empty=True, required=False
    )


class ExecuteRequestSerializer(serializers.Serializer):
    spec = DevelopmentSpecSerializer(required=False)


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
    token_preview = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = RepositoryLink
        fields = [
            "id",
            "provider",
            "repository",
            "base_url",
            "access_token",
            "token_preview",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "token_preview",
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
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        return RepositoryLink.objects.create(user=request.user, **validated_data)

    def get_token_preview(self, obj: RepositoryLink) -> str:
        return obj.token_preview()
