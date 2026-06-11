"""Global ASGI middleware for the e-commerce kit.

Listed outer→inner (first entry is the outermost layer). Edit this the same
way you edit ``bootstrap/providers.py``. Each framework middleware self-gates
on config, so listing one doesn't force it on.

App-specific middleware that needs custom config (locale, the kit's CSRF
exempt-paths, security headers) is added in ``bootstrap/app.py:create_asgi``
after ``into_asgi()`` so it sits outside this framework stack.
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
