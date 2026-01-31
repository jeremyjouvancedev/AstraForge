from rest_framework import serializers
from .models import AstraControlSession

class AstraControlSessionSerializer(serializers.ModelSerializer):
    sandbox_status = serializers.SerializerMethodField()

    class Meta:
        model = AstraControlSession
        fields = "__all__"
        read_only_fields = ["id", "user", "status", "state", "sandbox_session", "created_at", "updated_at"]

    def get_sandbox_status(self, obj):
        """Return the current status of the sandbox session."""
        if obj.sandbox_session:
            return obj.sandbox_session.status
        return None


class DocumentUploadSerializer(serializers.Serializer):
    """Serializer for uploading documents to an Astra Control session."""
    file = serializers.FileField(required=True, help_text="The document file to upload (max 10MB)")
    description = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        help_text="Optional description/context for this document"
    )

    def validate_file(self, value):
        """Validate file size and type."""
        # Max file size: 10MB
        max_size = 10 * 1024 * 1024
        if value.size > max_size:
            raise serializers.ValidationError(f"File size must not exceed 10MB. Current size: {value.size / (1024*1024):.2f}MB")

        # Allowed file extensions
        allowed_extensions = [
            'pdf', 'txt', 'csv', 'json', 'md', 'markdown',
            'py', 'js', 'jsx', 'ts', 'tsx', 'java', 'c', 'cpp', 'h', 'hpp',
            'html', 'css', 'xml', 'yaml', 'yml', 'toml', 'ini', 'conf',
            'sh', 'bash', 'sql', 'log',
            'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp',
            'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
            'zip', 'tar', 'gz'
        ]

        file_ext = value.name.split('.')[-1].lower() if '.' in value.name else ''
        if file_ext not in allowed_extensions:
            raise serializers.ValidationError(
                f"File type '.{file_ext}' is not allowed. Allowed types: {', '.join(allowed_extensions)}"
            )

        return value
