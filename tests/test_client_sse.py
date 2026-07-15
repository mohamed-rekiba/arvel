"""SSE streaming over the Http client (MockTransport — no network)."""

from __future__ import annotations

import httpx
import pytest

from arvel.client import Client, RequestFailed, ServerSentEvent


def _transport(handler: object) -> httpx.MockTransport:
    return httpx.MockTransport(handler)  # type: ignore[arg-type]


def _stream_handler(body: str, status: int = 200) -> object:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=body, headers={"content-type": "text/event-stream"})

    return handler


async def test_stream_yields_data_events() -> None:
    body = 'data: {"tok": "a"}\n\ndata: {"tok": "b"}\n\ndata: [DONE]\n\n'
    client = Client(transport=_transport(_stream_handler(body)))
    seen = [
        event.data
        async for event in client.stream("POST", "https://api.test/v1/chat", json={"stream": True})
    ]
    assert seen == ['{"tok": "a"}', '{"tok": "b"}', "[DONE]"]


async def test_stream_multiline_data_joined_with_newline() -> None:
    body = "data: line one\ndata: line two\n\n"
    client = Client(transport=_transport(_stream_handler(body)))
    events = [e async for e in client.stream("GET", "https://api.test/feed")]
    assert len(events) == 1
    assert events[0].data == "line one\nline two"


async def test_stream_event_type_id_and_comments() -> None:
    body = ": keep-alive ping\nevent: update\nid: 42\ndata: hi\n\n"
    client = Client(transport=_transport(_stream_handler(body)))
    events = [e async for e in client.stream("GET", "https://api.test/feed")]
    assert events == [events[0]]  # single event
    assert isinstance(events[0], ServerSentEvent)
    assert events[0].event == "update"
    assert events[0].id == "42"
    assert events[0].data == "hi"


async def test_stream_sets_accept_header() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["accept"] = request.headers["accept"]
        return httpx.Response(200, text="data: x\n\n")

    client = Client(transport=_transport(handler))
    _ = [e async for e in client.stream("GET", "https://api.test/feed")]
    assert captured["accept"] == "text/event-stream"


async def test_stream_raises_request_failed_on_error_status() -> None:
    client = Client(transport=_transport(_stream_handler("nope", status=429)))
    with pytest.raises(RequestFailed) as excinfo:
        _ = [e async for e in client.stream("POST", "https://api.test/chat")]
    assert excinfo.value.response.status() == 429
    assert excinfo.value.response.body() == "nope"  # body is read before raising
