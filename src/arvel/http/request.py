"""Request-scoped container middleware.

Pure ASGI middleware that creates a REQUEST-scoped child container
at the start of each HTTP request and closes it after the response.
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
    """Creates and closes a REQUEST-scoped child container per HTTP request.

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
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        child = await self._container.enter_scope(DIScope.REQUEST)

        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["container"] = child

        try:
            await self.app(scope, receive, send)
        finally:
            await child.close()
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
