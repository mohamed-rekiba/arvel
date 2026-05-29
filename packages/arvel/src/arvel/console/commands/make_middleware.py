"""``make:middleware`` — generate route-level HTTP middleware.

Arvel's middleware contract is a structural :class:`arvel.http.middleware.Middleware`
:class:`typing.Protocol`. Any class with an ``async def handle(self, request, call_next)``
satisfies it — no inheritance required.

Register the middleware on a route or route group; the kernel composes
the chain via ``arvel.support.Pipeline`` and calls
``await call_next(request)`` between every step.
"""

from __future__ import annotations

from typing import ClassVar

from arvel.console.commands._base_make import BaseMakeCommand
from arvel.support.str import Str

_TEMPLATE = '''"""{title} — route-level HTTP middleware."""

from __future__ import annotations

from typing import Any

from arvel.http.middleware import CallNext


class {title}:
    """Inspect or transform the request, then call ``call_next``."""

    async def handle(self, request: Any, call_next: CallNext) -> Any:
        # Pre-processing — read headers, check auth, etc.
        response = await call_next(request)
        # Post-processing — mutate response headers, log, etc.
        return response
'''


class MakeMiddlewareCommand(BaseMakeCommand):
    name: ClassVar[str] = "make:middleware"
    help: ClassVar[str] = "Generate HTTP middleware (handle(request, call_next))"
    _target_subdir: ClassVar[str] = "app/http/middleware"

    def _render(self, name: str) -> str:
        return _TEMPLATE.format(title=Str.pascal(name))
