"""GuardContract — abstract base class for pluggable authentication guards.

Each guard knows how to extract credentials from an ASGI scope,
validate them, and produce an AuthContext on success.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.responses import Response
    from starlette.types import Scope

    from arvel.auth.policy import AuthContext


class GuardContract(ABC):
    """Abstract base for authentication guards.

    Implementations:
        - ``JwtGuard``: validates Bearer JWT tokens
        - ``ApiKeyGuard``: validates X-API-Key headers
    """

    @abstractmethod
    async def authenticate(self, scope: Scope) -> AuthContext | None:
        """Attempt to authenticate from the ASGI scope.

        Returns an AuthContext on success, None if credentials are missing
        or invalid. Must NOT raise — return None instead.
        """

    @abstractmethod
    def error_response(self) -> Response:
        """Return the error response for failed authentication."""
