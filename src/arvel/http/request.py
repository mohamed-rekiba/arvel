"""Request-scoped container middleware.

Pure ASGI middleware that creates a REQUEST-scoped child container
at the start of each HTTP or WebSocket connection and closes it afterward.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.foundation.container import Container  # noqa: TC001
from arvel.foundation.container import Scope as DIScope

if TYPE_CHECKING:
    from collections.abc import Callable

    from starlette.types import ASGIApp, Receive, Scope, Send

    from arvel.http._types import MiddlewareHost


class RequestContainerMiddleware:
    """Creates and closes a REQUEST-scoped child container per HTTP request or WebSocket connection.

    Stores the child container at ``scope["state"]["container"]`` so that
    controller resolution and DI can access it.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        container: Container,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        self.app = app
        self._container = container
        self._on_close = on_close

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        child = self._container.enter_scope(DIScope.REQUEST)

        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["container"] = child

        try:
            await self.app(scope, receive, send)
        finally:
            try:
                await child.close()
            finally:
                if self._on_close is not None:
                    self._on_close()

    @classmethod
    def install(
        cls,
        app: MiddlewareHost,
        container: Container,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        """Install onto a FastAPI/Starlette app using add_middleware."""
        app.add_middleware(cls, container=container, on_close=on_close)
