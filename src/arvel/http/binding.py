"""arvel.http.binding — route/model binding resolution (H12 split from ``HttpKernel``).

Explicit bindings (``Route.model``/``bind_enum``) and implicit route-model binding share one
resolver, built once by the kernel and reused across requests. It holds the kernel's ``bindings``
dict **by reference** — ``routing/__init__.py`` mutates that dict after kernel construction
(``kernel.bindings.update(...)`` as routes register), so a snapshot would 404 a route registered
after the kernel is built.

Grounded in knowledge/port/04-http-kernel-middleware.md (route-adaptation + pipeline).
"""

from __future__ import annotations

import inspect
import typing
from typing import Any


class BindingMissing(Exception):
    """Internal control-flow signal: a route/model binding (explicit or implicit) didn't resolve.
    Caught in ``HttpKernel._dispatch`` so a route's ``.missing(callback)`` hook (if any) can render
    a custom response instead of the default 404."""


class BindingResolver:
    """Resolves explicit + implicit route-param bindings for one ``HttpKernel``.

    ``bindings`` is the kernel's own ``route-param -> resolver`` dict, held **by reference** (not
    copied) — routes registered after construction must still resolve."""

    def __init__(self, bindings: dict[str, Any]) -> None:
        self._bindings = bindings

    async def resolve_explicit(self, params: dict[str, Any]) -> None:
        """Resolve *explicit* route-param bindings (``Route.model``/``bind_enum``) in
        place; raises :class:`BindingMissing` on a miss (the kernel turns that into 404, or the
        route's own ``.missing(callback)`` response)."""
        for name, resolver in self._bindings.items():
            if name not in params:
                continue
            resolved = resolver(params[name])
            if inspect.isawaitable(resolved):
                resolved = await resolved
            if resolved is None:
                raise BindingMissing(name)
            params[name] = resolved

    async def resolve_implicit(
        self,
        handler: Any,
        params: dict[str, Any],
        key_fields: dict[str, str] | None = None,
        *,
        scope_bindings: bool = False,
        trashed_all: bool = False,
        trashed_params: frozenset[str] = frozenset(),
    ) -> None:
        """Implicit route-model binding: a path param
        whose handler type hint is a model (duck-typed: has ``resolve_route_binding``)
        is resolved to that model by its route key; raises :class:`BindingMissing` on a miss (see
        :meth:`resolve_explicit`). An inline ``{post:slug}`` route-key field (from ``key_fields``)
        overrides the model's default route key. Params already handled by an explicit binding are
        skipped. Duck-typing keeps the HTTP layer from importing the database layer.

        ``scope_bindings`` (H2, a route's ``.scope_bindings()``): once a param resolves to a model,
        a later param whose model exposes ``resolve_child_route_binding`` (duck-typed) resolves
        constrained to that parent instead of independently. ``trashed_all``/``trashed_params``
        (H3, ``.with_trashed()``) pass ``with_trashed=True`` through to a plain (unscoped)
        ``resolve_route_binding`` for the opted-in param(s) — only when opted in, so a duck-typed
        resolver that doesn't accept the kwarg (most test doubles) is never broken by it.
        """
        key_fields = key_fields or {}
        try:
            hints = typing.get_type_hints(inspect.unwrap(handler))
        except Exception:  # unresolvable / forward-ref hints: skip implicit binding
            return
        parent: Any = None
        for name in list(params):
            if name in self._bindings:  # an explicit binding already resolved this param
                continue
            annotation = hints.get(name)
            resolver = getattr(annotation, "resolve_route_binding", None)
            if resolver is None or not callable(resolver):
                continue
            child_resolver = getattr(annotation, "resolve_child_route_binding", None)
            if scope_bindings and parent is not None and callable(child_resolver):
                resolved = child_resolver(parent, params[name], key_fields.get(name))
            elif trashed_all or name in trashed_params:
                resolved = resolver(params[name], key_fields.get(name), with_trashed=True)
            else:
                resolved = resolver(params[name], key_fields.get(name))
            if inspect.isawaitable(resolved):
                resolved = await resolved
            if resolved is None:
                raise BindingMissing(name)
            params[name] = resolved
            parent = resolved
