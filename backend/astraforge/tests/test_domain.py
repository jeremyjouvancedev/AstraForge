from astraforge.domain.models.request import Request, RequestPayload, RequestState


def test_request_state_transitions():
    payload = RequestPayload(title="Test", description="", context={})
    request = Request(
        id="1",
        user_id="user-1",
        tenant_id="tenant",
        source="direct_user",
        sender="",
        payload=payload,
    )

    request.transition(RequestState.SPEC_READY)
    assert request.state is RequestState.SPEC_READY

    request.transition(RequestState.CHAT_REVIEWED)
    assert request.state is RequestState.CHAT_REVIEWED


def test_request_invalid_transition_raises():
    payload = RequestPayload(title="Test", description="", context={})
    request = Request(
        id="1",
        user_id="user-1",
        tenant_id="tenant",
        source="direct_user",
        sender="",
        payload=payload,
    )

    try:
        request.transition(RequestState.MR_OPENED)
    except ValueError:
        pass
    else:  # pragma: no cover - fail
        raise AssertionError("expected ValueError")


def test_request_transition_allows_reexecution_from_patch_ready():
    payload = RequestPayload(title="Test", description="", context={})
    request = Request(
        id="1",
        user_id="user-1",
        tenant_id="tenant",
        source="direct_user",
        sender="",
        payload=payload,
    )

    request.transition(RequestState.SPEC_READY)
    request.transition(RequestState.EXECUTING)
    request.transition(RequestState.PATCH_READY)
    request.transition(RequestState.EXECUTING)
    assert request.state is RequestState.EXECUTING
