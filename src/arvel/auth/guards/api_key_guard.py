"""ApiKeyGuard — validates X-API-Key header against a set of known keys."""

from __future__ import annotations

import hmac
from typing import TYPE_CHECKING

from starlette.responses import JSONResponse

from arvel.auth.contracts import GuardContract
from arvel.auth.policy import AuthContext

if TYPE_CHECKING:
    from starlette.types import Scope


class ApiKeyGuard(GuardContract):
    """Authenticates requests using a static API key header.

    Checks the ``X-API-Key`` header against a list of valid keys using
    constant-time comparison to prevent timing attacks.
    """

    def __init__(self, *, api_keys: list[str]) -> None:
        self._api_keys = api_keys

    async def authenticate(self, scope: Scope) -> AuthContext | None:
        if not self._api_keys:
            return None

        headers = dict(scope.get("headers", []))
        api_key = headers.get(b"x-api-key", b"").decode("latin-1")

        if not api_key:
            return None

        for valid_key in self._api_keys:
            if hmac.compare_digest(api_key, valid_key):
                return AuthContext(
                    user=None,
                    sub=f"apikey:{api_key[:8]}",
                    guard="api_key",
                )

        return None

    def error_response(self) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": "AUTH_REQUIRED", "message": "Valid API key required"}},
            status_code=401,
        )
