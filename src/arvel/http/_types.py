"""Internal type aliases and protocols for the HTTP layer."""

from __future__ import annotations

from typing import Any, Protocol


class MiddlewareHost(Protocol):
    """Structural subtype for any ASGI app that supports ``add_middleware()``."""

    def add_middleware(
        self,
        middleware_class: type[Any],
        *args: Any,
        **kwargs: Any,
    ) -> None: ...
