"""JwtGuard — validates Bearer JWT tokens from the Authorization header."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.responses import JSONResponse

from arvel.auth.contracts import GuardContract
from arvel.auth.policy import AuthContext

if TYPE_CHECKING:
    from collections.abc import Callable

    from starlette.types import Scope

    from arvel.auth.tokens import TokenService


class JwtGuard(GuardContract):
    """Authenticates requests using Bearer JWT tokens.

    Extracts the token from the ``Authorization: Bearer <token>`` header,
    validates it via ``TokenService``, and builds an ``AuthContext``.
    """

    def __init__(
        self,
        *,
        token_service: TokenService,
        claims_mapper: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self._token_service = token_service
        self._claims_mapper = claims_mapper

    async def authenticate(self, scope: Scope) -> AuthContext | None:
        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode("latin-1")

        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[7:]
        try:
            payload = self._token_service.decode_token(token)
        except Exception:
            return None

        if self._claims_mapper is not None:
            payload = self._claims_mapper(payload)

        sub = payload.get("sub", "")
        roles = payload.get("roles", [])
        groups = payload.get("groups", [])

        return AuthContext(
            user=None,
            sub=sub,
            roles=roles,
            groups=groups,
            claims=payload,
            guard="jwt",
        )

    def error_response(self) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": "AUTH_REQUIRED", "message": "Authentication required"}},
            status_code=401,
        )
