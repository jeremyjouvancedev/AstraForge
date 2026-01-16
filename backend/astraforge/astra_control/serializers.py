from rest_framework import serializers
from .models import AstraControlSession

class AstraControlSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AstraControlSession
        fields = "__all__"
        read_only_fields = ["id", "user", "status", "state", "sandbox_session", "created_at", "updated_at"]
