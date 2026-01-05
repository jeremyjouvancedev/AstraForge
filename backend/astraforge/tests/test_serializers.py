import pytest
from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.test import APIRequestFactory

from astraforge.accounts.models import Workspace
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
    workspace = Workspace.ensure_default_for_user(user)
    repo_link = RepositoryLink.objects.create(
        user=user,
        workspace=workspace,
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
    assert request_obj.tenant_id == workspace.uid
    assert rendered["tenant_id"] == workspace.uid
    assert rendered["payload"]["title"] == "Add retry logic"
    assert rendered["payload"]["description"] == payload["prompt"]
    assert rendered["metadata"]["prompt"] == payload["prompt"]
    assert rendered["project"]["id"] == str(repo_link.id)
    assert rendered["metadata"]["workspace"]["uid"] == workspace.uid
    assert rendered["state"] == request_obj.state.value
    assert "access_token" not in rendered["project"]


def test_request_serializer_includes_llm_config():
    factory = APIRequestFactory()
    user = get_user_model().objects.create_user(
        username="serializer-llm-user",
        email="llm-owner@example.com",
        password="pass12345",
    )
    workspace = Workspace.ensure_default_for_user(user)
    repo_link = RepositoryLink.objects.create(
        user=user,
        workspace=workspace,
        provider=RepositoryLink.Provider.GITHUB,
        repository="org/project",
        access_token="token-123",
    )
    request = factory.post("/requests/")
    request.user = user
    payload = {
        "tenant_id": "tenant-default",
        "source": "direct_user",
        "sender": "llm-owner@example.com",
        "project_id": str(repo_link.id),
        "prompt": "Run with a different provider.",
        "llm_provider": "ollama",
        "llm_model": "gpt-oss:120b",
    }
    serializer = RequestSerializer(data=payload, context={"request": request})
    assert serializer.is_valid(), serializer.errors
    request_obj = serializer.save()

    llm_meta = request_obj.metadata.get("llm")
    assert llm_meta == {"provider": "ollama", "model": "gpt-oss:120b"}


class DummySerializer(serializers.Serializer):
    field = serializers.CharField()
