"""``SignedMiddleware`` — guard routes behind ``URL.signed_route()``."""

from __future__ import annotations

from typing import Any

from arvel.http._middleware_core import CallNext
from arvel.http.exceptions import AuthorizationException


class SignedMiddleware:
    """Aborts with 403 unless the request URL bears a valid HMAC signature.

    Pair with ``arvel.routing.URL.signed_route()`` to produce email-verification
    or password-reset links that can't be tampered with.
    """

    async def handle(self, request: Any, call_next: CallNext) -> Any:
        # Lazy import — routing depends on http via Pipeline; keep the cycle out.
        from arvel.routing import URL

        if not URL.has_valid_signature(request):
            raise AuthorizationException("Invalid or expired URL signature.")
        return await call_next(request)


__all__ = ["SignedMiddleware"]
