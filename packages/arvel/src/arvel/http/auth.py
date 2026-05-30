"""Authentication primitives re-exported at arvel.http.auth for convenience."""

from __future__ import annotations

from arvel.auth.guard import Guard, UserResolver
from arvel.auth.guards.jwt import JwtGuard
from arvel.auth.guards.session import SessionGuard

__all__ = [
    "Guard",
    "JwtGuard",
    "SessionGuard",
    "UserResolver",
]
