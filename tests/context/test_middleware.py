"""Tests for context middleware — FR-001.11 / FR-001.12."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arvel.context.context_store import Context

if TYPE_CHECKING:
    from collections.abc import MutableMapping

    from starlette.types import ASGIApp, Receive, Scope, Send


class TestContextMiddleware:
    """FR-001.11: ContextMiddleware resets context per request."""

    async def test_context_is_clean_at_request_start(
        self, echo_app: ASGIApp, make_scope: Any
    ) -> None:
        from arvel.context.middleware import ContextMiddleware

        Context.add("stale", "data")

        captured: dict[str, Any] = {}

        async def capturing_app(scope: Scope, receive: Receive, send: Send) -> None:
            captured.update(Context.all())
            await echo_app(scope, receive, send)

        middleware = ContextMiddleware(capturing_app)

        async def receive() -> MutableMapping[str, Any]:
            return {"type": "http.request", "body": b""}

        responses: list[MutableMapping[str, Any]] = []

        async def send(msg: MutableMapping[str, Any]) -> None:
            responses.append(msg)

        scope = make_scope()
        await middleware(scope, receive, send)
        assert "stale" not in captured

    async def test_context_does_not_leak_between_requests(
        self, echo_app: ASGIApp, make_scope: Any
    ) -> None:
        from arvel.context.middleware import ContextMiddleware

        captured_values: list[dict[str, Any]] = []

        async def capturing_app(scope: Scope, receive: Receive, send: Send) -> None:
            if scope["path"] == "/first":
                Context.add("req", "first")
            captured_values.append(dict(Context.all()))
            await echo_app(scope, receive, send)

        middleware = ContextMiddleware(capturing_app)

        async def receive() -> MutableMapping[str, Any]:
            return {"type": "http.request", "body": b""}

        async def send(msg: MutableMapping[str, Any]) -> None:
            pass

        await middleware(make_scope(path="/first"), receive, send)
        await middleware(make_scope(path="/second"), receive, send)

        assert captured_values[0].get("req") == "first"
        assert "req" not in captured_values[1]

    async def test_non_http_scope_passes_through(self, echo_app: ASGIApp) -> None:
        from arvel.context.middleware import ContextMiddleware

        called = False

        async def lifespan_app(scope: Scope, receive: Receive, send: Send) -> None:
            nonlocal called
            called = True

        middleware = ContextMiddleware(lifespan_app)
        scope: dict[str, Any] = {
            "type": "lifespan",
            "asgi": {"version": "3.0"},
        }

        async def receive() -> MutableMapping[str, Any]:
            return {"type": "lifespan.startup"}

        async def send(msg: MutableMapping[str, Any]) -> None:
            pass

        await middleware(scope, receive, send)
        assert called is True
