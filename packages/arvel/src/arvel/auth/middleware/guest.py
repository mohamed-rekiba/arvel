"""GuestMiddleware — redirect authenticated users away from guest-only routes."""

from __future__ import annotations

from typing import Any

from starlette.responses import RedirectResponse


class GuestMiddleware:
    def __init__(self, *, redirect_to: str = "/") -> None:
        self._redirect_to = redirect_to

    async def handle(self, request: Any, call_next: Any) -> Any:
        user = getattr(getattr(request, "state", None), "user", None)
        if user is not None:
            return RedirectResponse(url=self._redirect_to, status_code=302)
        return await call_next(request)
