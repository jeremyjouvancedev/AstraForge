"""Serializers bridging HTTP payloads and domain objects."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import serializers

from astraforge.accounts.models import ApiKey
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
    payload = RequestPayloadSerializer()

    def create(self, validated_data):
        payload_data = validated_data.pop("payload")
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
        return Request(payload=payload, **validated_data)

    def to_representation(self, instance: Request):
        return {
            "id": instance.id,
            "tenant_id": instance.tenant_id,
            "source": instance.source,
            "sender": instance.sender,
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
            "metadata": instance.metadata,
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
