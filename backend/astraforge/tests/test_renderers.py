from astraforge.interfaces.rest.renderers import EventStreamRenderer


def test_event_stream_renderer_passthrough():
    renderer = EventStreamRenderer()

    assert renderer.media_type == "text/event-stream"
    payload = b"event: message\n\ndata: {}\n\n"
    assert renderer.render(payload) == payload
