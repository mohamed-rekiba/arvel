"""VerifiedMiddleware — block users whose email is not verified."""

from __future__ import annotations

from typing import Any

from arvel.auth.exceptions import AuthorizationException, UnauthenticatedException


class VerifiedMiddleware:
    async def handle(self, request: Any, call_next: Any) -> Any:
        user = getattr(getattr(request, "state", None), "user", None)
        # Not logged in is a 401 — re-authenticate. Logged in but unverified is a
        # 403 — re-authenticating won't help; the user has to verify their email.
        if user is None:
            raise UnauthenticatedException("Not authenticated.")
        if not getattr(user, "email_verified_at", None):
            raise AuthorizationException("Email address is not verified.")
        return await call_next(request)
