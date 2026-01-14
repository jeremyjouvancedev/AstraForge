import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import serializers
from rest_framework.test import APIRequestFactory

from astraforge.accounts.models import Workspace
from astraforge.quotas.services import get_quota_service
from astraforge.sandbox.models import SandboxSession
from astraforge.sandbox.serializers import SandboxSessionCreateSerializer

pytestmark = pytest.mark.django_db


@override_settings(
    WORKSPACE_QUOTAS_ENABLED=True,
    WORKSPACE_PLAN_LIMITS={
        "trial": {
            "requests_per_month": 5,
            "sandbox_sessions_per_month": 1,
            "sandbox_concurrent": 1,
        }
    },
)
def test_sandbox_quota_blocks_additional_sessions():
    user = get_user_model().objects.create_user(username="sandboxer", password="pass12345")
    workspace = Workspace.ensure_default_for_user(user)
    factory = APIRequestFactory()
    request = factory.post("/sandbox/sessions/", {})
    request.user = user
    get_quota_service(refresh=True)

    serializer = SandboxSessionCreateSerializer(
        data={"mode": SandboxSession.Mode.DOCKER},
        context={"request": request},
    )
    serializer.is_valid(raise_exception=True)
    session = serializer.save()
    assert session.workspace == workspace

    serializer = SandboxSessionCreateSerializer(
        data={"mode": SandboxSession.Mode.DOCKER},
        context={"request": request},
    )
    serializer.is_valid(raise_exception=True)
    with pytest.raises(serializers.ValidationError) as excinfo:
        serializer.save()
    assert "active sandboxes" in str(excinfo.value).lower()
