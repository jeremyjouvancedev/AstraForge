import pytest
from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.test import APIRequestFactory

from astraforge.integrations.models import RepositoryLink
from astraforge.interfaces.rest.serializers import RequestSerializer


pytestmark = pytest.mark.django_db


def test_request_serializer_roundtrip():
    factory = APIRequestFactory()
    user = get_user_model().objects.create_user(
        username="serializer-user",
        email="owner@example.com",
        password="pass12345",
    )
    repo_link = RepositoryLink.objects.create(
        user=user,
        provider=RepositoryLink.Provider.GITHUB,
        repository="org/project",
        access_token="token-123",
    )
    request = factory.post("/requests/")
    request.user = user
    payload = {
        "tenant_id": "tenant-default",
        "source": "direct_user",
        "sender": "owner@example.com",
        "project_id": str(repo_link.id),
        "prompt": "Add retry logic\nHandle intermittent network errors.",
    }
    serializer = RequestSerializer(data=payload, context={"request": request})
    assert serializer.is_valid(), serializer.errors
    request_obj = serializer.save()
    rendered = serializer.to_representation(request_obj)
    assert rendered["payload"]["title"] == "Add retry logic"
    assert rendered["payload"]["description"] == payload["prompt"]
    assert rendered["metadata"]["prompt"] == payload["prompt"]
    assert rendered["project"]["id"] == str(repo_link.id)
    assert rendered["state"] == request_obj.state.value
    assert "access_token" not in rendered["project"]


class DummySerializer(serializers.Serializer):
    field = serializers.CharField()
