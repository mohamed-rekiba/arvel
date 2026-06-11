"""Declared global ASGI middleware for this application.

Listed outer→inner: the first entry is the outermost layer, the last is the
innermost (closest to your route handlers). Reorder, add, or remove entries
the same way you edit ``bootstrap/providers.py``.

Each framework middleware self-gates on config — listing one doesn't force it
on. ``ThrottleLoginMiddleware`` and ``CsrfDoubleSubmitMiddleware`` only mount
when auth is registered; ``TrustProxiesMiddleware`` only when ``TRUSTED_PROXIES``
is set; ``MaintenanceModeMiddleware`` only when its manager is bound.

``ArvelScopeMiddleware`` is pinned innermost by the framework whether or not you
list it — the per-request DI scope must wrap your handlers.

Add your own middleware by subclassing ``arvel.contracts.GlobalMiddleware`` and
implementing ``boot(cls, app, container)``.
"""

from __future__ import annotations

from arvel.auth.middleware.csrf_double_submit import CsrfDoubleSubmitMiddleware
from arvel.auth.middleware.throttle_login import ThrottleLoginMiddleware
from arvel.context import ContextMiddleware, DeferredTaskMiddleware
from arvel.contracts import GlobalMiddleware
from arvel.http.middleware import ArvelScopeMiddleware, TrustProxiesMiddleware
from arvel.maintenance import MaintenanceModeMiddleware
from arvel.observability import ObservabilityMiddleware

middleware: list[type[GlobalMiddleware]] = [
    TrustProxiesMiddleware,
    MaintenanceModeMiddleware,
    ThrottleLoginMiddleware,
    CsrfDoubleSubmitMiddleware,
    ObservabilityMiddleware,
    ContextMiddleware,
    DeferredTaskMiddleware,
    ArvelScopeMiddleware,
]
