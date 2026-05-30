"""VerifiedMiddleware — block users whose email is not verified."""

from __future__ import annotations

from typing import Any

from arvel.auth.exceptions import UnauthenticatedException


class VerifiedMiddleware:
    async def handle(self, request: Any, call_next: Any) -> Any:
        user = getattr(getattr(request, "state", None), "user", None)
        if user is None or not getattr(user, "email_verified_at", None):
            raise UnauthenticatedException("Email address is not verified.")
        return await call_next(request)
