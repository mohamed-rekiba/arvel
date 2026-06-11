"""ArvelScopeMiddleware — creates a per-request DI scope."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from arvel.contracts.middleware import GlobalMiddleware

if TYPE_CHECKING:
    from fastapi import FastAPI

    from arvel.container import Container


class ArvelScopeMiddleware(GlobalMiddleware):
    """Attaches the root container as request.state.arvel_scope.

    Pinned as the innermost layer by Application.into_asgi so every
    Depends(dep(...)) call has a scope to resolve from.

    Full per-request child containers are a future enhancement (note).
    For now, the root container serves as the scope so dep resolves correctly.
    """

    def __init__(self, app: ASGIApp, *, container: Container) -> None:
        self.app = app
        self._container = container

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            request = Request(scope)
            if hasattr(request, "state"):
                request.state.arvel_scope = self._container
        await self.app(scope, receive, send)

    @classmethod
    def boot(cls, app: FastAPI, container: Container) -> None:
        app.add_middleware(cls, container=container)
