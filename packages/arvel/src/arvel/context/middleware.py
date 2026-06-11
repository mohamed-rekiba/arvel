"""ASGI middleware that scopes ``Context`` to a request and drains deferred work.

Two pure-ASGI middlewares (no Starlette ``BaseHTTPMiddleware`` — it buffers
streaming bodies):

- ``ContextMiddleware`` binds a fresh ``ContextRepository`` per request and resets
  it on teardown so keys never leak into the next request. It seeds ``request_id``
  from the observability context when one is already set.
- ``DeferredTaskMiddleware`` runs callbacks registered via ``defer()`` after the
  response is sent. It must sit *inside* ``ContextMiddleware`` so the repository is
  still bound while deferred work runs.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

from arvel.container.errors import BindingResolutionError
from arvel.context.repository import (
    ContextRepository,
    bind_repository,
    current_repository,
    reset_repository,
)
from arvel.contracts.middleware import GlobalMiddleware
from arvel.logging.facade import Log
from arvel.observability.config import ObservabilityConfig
from arvel.observability.context import get_request_context

if TYPE_CHECKING:
    from fastapi import FastAPI
    from starlette.types import ASGIApp, Receive, Scope, Send

    from arvel.container import Container


def _request_middleware_enabled(container: Container) -> bool:
    """Whether the request-scoped middleware layer is on (tracks observability)."""
    try:
        config = container.make(ObservabilityConfig)
    except BindingResolutionError:
        config = ObservabilityConfig()
    return config.request_middleware_enabled


class ContextMiddleware(GlobalMiddleware):
    """Bind a fresh ``ContextRepository`` for the lifetime of each request."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    @classmethod
    def boot(cls, app: FastAPI, container: Container) -> None:
        if _request_middleware_enabled(container):
            app.add_middleware(cls)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        repo = ContextRepository()
        self._seed_request_id(repo)
        token = bind_repository(repo)
        try:
            await self._app(scope, receive, send)
        finally:
            reset_repository(token)

    def _seed_request_id(self, repo: ContextRepository) -> None:
        ctx = get_request_context()
        if ctx.request_id:
            repo.add("request_id", ctx.request_id)


class DeferredTaskMiddleware(GlobalMiddleware):
    """Drain ``defer()`` callbacks after the response, isolating each failure."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    @classmethod
    def boot(cls, app: FastAPI, container: Container) -> None:
        if _request_middleware_enabled(container):
            app.add_middleware(cls)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        try:
            await self._app(scope, receive, send)
        finally:
            await _drain_deferred()


async def _drain_deferred() -> None:
    repo = current_repository()
    for callback in repo.deferred():
        try:
            result = callback()
            if inspect.isawaitable(result):
                await result
        except Exception as exc:  # noqa: BLE001 — one bad deferred task must not stop the rest
            Log.error("context.deferred_failed", exc=exc)


__all__ = ["ContextMiddleware", "DeferredTaskMiddleware"]
