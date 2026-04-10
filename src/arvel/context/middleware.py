"""ASGI middleware for context lifecycle and deferred task execution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arvel.context.context_store import Context
from arvel.context.deferred import DeferredCollector, _execute_deferred

_SCOPE_CONTEXT_KEY = "arvel_context"

if TYPE_CHECKING:
    from collections.abc import MutableMapping

    from starlette.types import ASGIApp, Receive, Scope, Send


class ContextMiddleware:
    """ASGI middleware that resets the context store per request.

    Flushes both visible and hidden context at the start of each HTTP
    request to prevent cross-request leakage. Before flushing, snapshots
    the visible context into the ASGI ``scope`` so that exception handlers
    running *after* middleware teardown can still read all context keys
    (``request_id``, ``tenant_id``, ``user_id``, etc.).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        Context.flush()
        try:
            await self.app(scope, receive, send)
        finally:
            scope[_SCOPE_CONTEXT_KEY] = Context.all()
            Context.flush()


class DeferredTaskMiddleware:
    """ASGI middleware that runs deferred tasks after the response is sent.

    Collects tasks registered via ``defer()`` during request handling,
    then executes them after the final response body chunk is transmitted.
    """

    def __init__(self, app: ASGIApp, *, timeout: float = 30.0) -> None:
        self.app = app
        self._timeout = timeout

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        collector = DeferredCollector()
        collector.install()

        async def send_wrapper(message: MutableMapping[str, Any]) -> None:
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            tasks = collector.drain()
            if tasks:
                await _execute_deferred(tasks, self._timeout)
