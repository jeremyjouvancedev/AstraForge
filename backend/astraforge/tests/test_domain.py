from astraforge.domain.models.request import Request, RequestPayload, RequestState


def test_request_state_transitions():
    payload = RequestPayload(title="Test", description="", context={})
    request = Request(
        id="1", tenant_id="tenant", source="direct_user", sender="", payload=payload
    )

    request.transition(RequestState.SPEC_READY)
    assert request.state is RequestState.SPEC_READY

    request.transition(RequestState.CHAT_REVIEWED)
    assert request.state is RequestState.CHAT_REVIEWED


def test_request_invalid_transition_raises():
    payload = RequestPayload(title="Test", description="", context={})
    request = Request(
        id="1", tenant_id="tenant", source="direct_user", sender="", payload=payload
    )

    try:
        request.transition(RequestState.MR_OPENED)
    except ValueError:
        pass
    else:  # pragma: no cover - fail
        raise AssertionError("expected ValueError")
