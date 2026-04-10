"""Middleware protocol, alias resolution, and group expansion.

All Arvel middleware is pure ASGI — no BaseHTTPMiddleware.
Aliases are resolved at boot time via importlib. Groups are expanded
recursively before individual alias resolution.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from arvel.http.exceptions import MiddlewareResolutionError
from arvel.logging import Log

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

    from arvel.foundation.container import Container

logger = Log.named("arvel.http.middleware")


@runtime_checkable
class Middleware(Protocol):
    """Protocol for pure ASGI middleware.

    Implementations receive the next ASGI app in the chain via ``__init__``
    and must call ``await self.app(scope, receive, send)`` to continue.
    """

    app: ASGIApp

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None: ...


@runtime_checkable
class TerminableMiddleware(Protocol):
    """Protocol for middleware with a post-response terminate hook.

    ``terminate`` runs after the response is fully sent. Exceptions in
    ``terminate`` are logged but don't affect the response.
    """

    app: ASGIApp

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None: ...

    async def terminate(self) -> None: ...


class MiddlewareStack:
    """Resolves middleware aliases to concrete classes at boot time.

    Supports middleware groups: a group name maps to a list of aliases.
    When a name matches a group, all aliases in the group are expanded
    recursively before individual alias resolution.

    Attributes:
        aliases: Map of short names to dotted import paths.
        groups: Map of group names to lists of alias names.
    """

    def __init__(
        self,
        aliases: dict[str, str] | None = None,
        groups: dict[str, list[str]] | None = None,
    ) -> None:
        self._aliases = aliases or {}
        self._groups = groups or {}
        self._resolved: dict[str, type] = {}

    def expand(self, names: list[str]) -> list[str]:
        """Expand group names into individual alias names recursively.

        Non-group names pass through unchanged. Detects circular group
        references to prevent infinite loops.
        """
        result: list[str] = []
        seen: set[str] = set()
        self._expand_into(names, result, seen)
        return result

    def _expand_into(self, names: list[str], result: list[str], seen: set[str]) -> None:
        for name in names:
            if name in self._groups:
                if name in seen:
                    raise MiddlewareResolutionError(
                        f"Circular middleware group reference: '{name}'",
                        alias=name,
                    )
                seen.add(name)
                self._expand_into(self._groups[name], result, seen)
                seen.discard(name)
            else:
                result.append(name)

    def resolve(self, names: list[str]) -> list[type]:
        """Resolve a list of middleware alias names to their concrete classes.

        Group names are expanded first. Individual aliases are then resolved
        via importlib.

        Raises:
            MiddlewareResolutionError: If an alias isn't registered or the
                class path can't be imported.
        """
        expanded = self.expand(names)
        result: list[type] = []

        for name in expanded:
            if name in self._resolved:
                result.append(self._resolved[name])
                continue

            class_path = self._aliases.get(name)
            if class_path is None:
                raise MiddlewareResolutionError(
                    f"Unknown middleware alias '{name}' — not found in middleware_aliases config",
                    alias=name,
                )

            cls = self._import_class(name, class_path)
            self._resolved[name] = cls
            result.append(cls)

        return result

    def _import_class(self, alias: str, class_path: str) -> type:
        parts = class_path.rsplit(".", 1)
        if len(parts) != 2:
            raise MiddlewareResolutionError(
                f"Invalid class path for middleware alias '{alias}': "
                f"'{class_path}' — expected 'module.ClassName'",
                alias=alias,
                class_path=class_path,
            )

        module_path, class_name = parts
        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            raise MiddlewareResolutionError(
                f"Cannot import module '{module_path}' for middleware alias '{alias}': {e}",
                alias=alias,
                class_path=class_path,
            ) from e

        cls = getattr(module, class_name, None)
        if cls is None:
            raise MiddlewareResolutionError(
                f"Class '{class_name}' not found in module '{module_path}' "
                f"for middleware alias '{alias}'",
                alias=alias,
                class_path=class_path,
            )

        return cls


class RouteMiddlewareWrapper:
    """ASGI app that wraps a route endpoint with resolved per-route middleware.

    Builds an onion around the inner app at construction time so that
    each request through this wrapper passes through all route-level
    middleware in declared order.
    """

    def __init__(self, app: ASGIApp, *, middleware_classes: list[type]) -> None:
        chain = app
        for cls in reversed(middleware_classes):
            chain = cls(chain)
        self._chain = chain

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self._chain(scope, receive, send)


class RequestScopeMiddleware:
    """ASGI middleware that creates a request-scoped DI container per request.

    Enters REQUEST scope on the app container, stores the scoped container
    in ``scope["state"]["container"]``, and closes it when the request ends.
    """

    def __init__(self, app: ASGIApp, *, container: Container) -> None:
        self.app = app
        self._container = container

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        from arvel.foundation.container import Scope as DIScope

        request_container = await self._container.enter_scope(DIScope.REQUEST)
        scope.setdefault("state", {})
        scope["state"]["container"] = request_container
        try:
            await self.app(scope, receive, send)
        finally:
            await request_container.close()
