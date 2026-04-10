"""Tests for request-ID middleware — FR-013 to FR-019, SEC-005."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest

from arvel.observability.request_id import (
    RequestIdMiddleware,
    get_request_id,
    request_id_var,
)

if TYPE_CHECKING:
    from collections.abc import MutableMapping


async def _fake_receive() -> MutableMapping[str, Any]:
    return {"type": "http.request", "body": b""}


async def _noop_send(message: MutableMapping[str, Any]) -> None:
    pass


class TestRequestIdVar:
    def test_get_request_id_returns_empty_when_not_set(self) -> None:
        """FR-016: ContextVar is accessible; returns empty/None when not in request."""
        result = get_request_id()
        assert result == "" or result is None

    def test_get_request_id_returns_value_when_set(self) -> None:
        """FR-016: ContextVar returns the set value."""
        token = request_id_var.set("abc-123")
        try:
            assert get_request_id() == "abc-123"
        finally:
            request_id_var.reset(token)


class TestRequestIdMiddleware:
    @pytest.mark.anyio
    async def test_generates_uuid_when_no_header(self) -> None:
        """FR-013: generates a UUID4 request ID for every request."""
        captured_headers: dict[str, str] = {}

        async def app(scope, receive, send):
            rid = get_request_id()
            assert rid != ""
            uuid.UUID(rid)

            async def send_wrapper(message):
                if message["type"] == "http.response.start":
                    for key, val in message.get("headers", []):
                        captured_headers[key.decode()] = val.decode()
                await send(message)

            await send_wrapper(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [[b"content-type", b"text/plain"]],
                }
            )
            await send({"type": "http.response.body", "body": b"ok"})

        mw = RequestIdMiddleware(app)
        scope = {"type": "http", "headers": []}

        async def receive():
            return {"type": "http.request", "body": b""}

        sent_messages: list[dict] = []

        async def send(message):
            sent_messages.append(message)

        await mw(scope, receive, send)

        response_headers = {}
        for msg in sent_messages:
            if msg["type"] == "http.response.start":
                for k, v in msg.get("headers", []):
                    response_headers[k.decode() if isinstance(k, bytes) else k] = (
                        v.decode() if isinstance(v, bytes) else v
                    )

        assert "x-request-id" in response_headers
        uuid.UUID(response_headers["x-request-id"])

    @pytest.mark.anyio
    async def test_uses_valid_incoming_header(self) -> None:
        """FR-014: uses incoming X-Request-ID if it's a valid UUID."""
        incoming_id = str(uuid.uuid4())
        captured_id = ""

        async def app(scope, receive, send):
            nonlocal captured_id
            captured_id = get_request_id()
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            await send({"type": "http.response.body", "body": b"ok"})

        mw = RequestIdMiddleware(app)
        scope = {
            "type": "http",
            "headers": [(b"x-request-id", incoming_id.encode())],
        }

        await mw(scope, _fake_receive, _noop_send)
        assert captured_id == incoming_id

    @pytest.mark.anyio
    async def test_rejects_invalid_incoming_header(self) -> None:
        """FR-019: invalid X-Request-ID discarded, fresh UUID generated."""
        captured_id = ""

        async def app(scope, receive, send):
            nonlocal captured_id
            captured_id = get_request_id()
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            await send({"type": "http.response.body", "body": b"ok"})

        mw = RequestIdMiddleware(app)
        scope = {
            "type": "http",
            "headers": [(b"x-request-id", b"not-a-uuid")],
        }

        await mw(scope, _fake_receive, _noop_send)
        assert captured_id != "not-a-uuid"
        uuid.UUID(captured_id)

    @pytest.mark.anyio
    async def test_response_includes_request_id_header(self) -> None:
        """FR-015: response includes X-Request-ID header."""
        sent_messages: list[dict] = []

        async def app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [[b"content-type", b"text/plain"]],
                }
            )
            await send({"type": "http.response.body", "body": b"ok"})

        mw = RequestIdMiddleware(app)
        scope = {"type": "http", "headers": []}

        async def send(message):
            sent_messages.append(message)

        await mw(scope, _fake_receive, send)

        response_headers = {}
        for msg in sent_messages:
            if msg["type"] == "http.response.start":
                for k, v in msg.get("headers", []):
                    key = k.decode() if isinstance(k, bytes) else k
                    val = v.decode() if isinstance(v, bytes) else v
                    response_headers[key] = val

        assert "x-request-id" in response_headers

    @pytest.mark.anyio
    async def test_passthrough_for_non_http_scope(self) -> None:
        """Non-HTTP scopes (lifespan) pass through without request-ID."""
        called = False

        async def app(scope, receive, send):
            nonlocal called
            called = True

        mw = RequestIdMiddleware(app)
        scope = {"type": "lifespan", "headers": []}
        await mw(scope, _fake_receive, _noop_send)
        assert called is True
