"""VerifiedMiddleware — blocks unverified users from protected routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send


class VerifiedMiddleware:
    """ASGI middleware that requires email verification.

    Checks ``scope["state"]["email_verified"]`` (set by the auth layer).
    Returns 403 if the user is not verified.

    Args:
        app: The next ASGI app in the chain.
        testing: If True, also reads the ``X-Test-Verified`` header.
            **Never enable in production** — it would let any client
            bypass verification by setting a header.
    """

    def __init__(self, app: ASGIApp, *, testing: bool = False) -> None:
        self.app = app
        self._testing = testing

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        state: dict[str, Any] = scope.get("state", {})
        is_verified = state.get("email_verified", False)

        if self._testing and not is_verified:
            headers = dict(scope.get("headers", []))
            test_verified = headers.get(b"x-test-verified", b"").decode("latin-1")
            if test_verified:
                is_verified = test_verified.lower() == "true"

        if not is_verified:
            response = JSONResponse(
                {
                    "error": {
                        "code": "EMAIL_NOT_VERIFIED",
                        "message": "Please verify your email address before continuing",
                    }
                },
                status_code=403,
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
