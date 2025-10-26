from rest_framework import serializers

from astraforge.interfaces.rest.serializers import RequestSerializer


def test_request_serializer_roundtrip():
    payload = {
        "payload": {
            "title": "Add retry logic",
            "description": "Handle intermittent network errors.",
            "context": {"module": "ingestion/data_loader.py"},
            "attachments": [],
        }
    }
    serializer = RequestSerializer(data=payload)
    assert serializer.is_valid(), serializer.errors
    request_obj = serializer.save()
    rendered = serializer.to_representation(request_obj)
    assert rendered["payload"]["title"] == "Add retry logic"
    assert rendered["state"] == request_obj.state.value


class DummySerializer(serializers.Serializer):
    field = serializers.CharField()
