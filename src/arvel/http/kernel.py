"""HTTP Kernel — global middleware stack orchestration.

The kernel owns the outermost ASGI middleware layer. It wraps the FastAPI
app with global middleware sorted by priority (lower = earlier).
Terminable middleware instances have their ``terminate()`` called after the
response is sent, in reverse order (last-in-first-terminate).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.logging import Log

if TYPE_CHECKING:
    from arvel.http._types import MiddlewareHost

logger = Log.named("arvel.http.kernel")


class HttpKernel:
    """Orchestrates the global middleware stack.

    Middleware is added via :meth:`add_global_middleware` with a priority
    value. When :meth:`mount` is called, middleware is wrapped around the
    FastAPI app in priority order (lowest first = outermost).
    """

    def __init__(self) -> None:
        self._middleware: list[tuple[type, int]] = []
        self._registered_classes: set[type] = set()

    @property
    def global_middleware(self) -> list[tuple[type, int]]:
        return list(self._middleware)

    def add_global_middleware(self, middleware_cls: type, *, priority: int = 50) -> None:
        """Register a global middleware class with a priority.

        Raises:
            ValueError: If the middleware class is already registered.
        """
        if middleware_cls in self._registered_classes:
            raise ValueError(f"Middleware {middleware_cls.__name__} is already registered")
        self._registered_classes.add(middleware_cls)
        self._middleware.append((middleware_cls, priority))

    def sorted_middleware(self) -> list[tuple[type, int]]:
        """Return middleware sorted by priority (lowest first)."""
        return sorted(self._middleware, key=lambda x: x[1])

    def mount(self, app: MiddlewareHost) -> None:
        """Register global middleware on a FastAPI/Starlette app.

        Middleware is added in reverse priority order so that the lowest
        priority number ends up outermost (runs first on request, last on
        response — onion model). Uses ``app.add_middleware()`` for compatibility
        with FastAPI's TestClient.
        """
        for middleware_cls, _priority in reversed(self.sorted_middleware()):
            app.add_middleware(middleware_cls)
