"""TokenGuard — Sanctum-style personal access token authentication.

Security:
- Hashes the incoming plain-text token with SHA-256 before DB lookup.
- Uses hmac.compare_digest for timing-safe comparison.
- Rejects tokens where expires_at is in the past.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from arvel.auth.guard import Guard
from arvel.auth.mixins import Authenticatable


@runtime_checkable
class TokenRepository(Protocol):
    async def find_by_hash(self, token_hash: str) -> Any | None: ...
    async def touch(self, token: Any) -> None: ...


@runtime_checkable
class UserRepository(Protocol):
    async def find(self, type_: str, id_: str) -> Any | None: ...


class TokenGuard(Guard):
    def __init__(
        self,
        *,
        token_repository: TokenRepository,
        user_repository: UserRepository,
    ) -> None:
        self._token_repo = token_repository
        self._user_repo = user_repository

    async def user(self, request: Any) -> Any | None:
        plain = self._extract_bearer(request)
        if plain is None:
            return None

        record = await self._resolve_record(plain)
        if record is None:
            return None

        user = await self._user_repo.find(record.tokenable_type, record.tokenable_id)
        if user is None:
            return None
        # `resolved` carries the isinstance narrowing so `user` stays broad for
        # the HasApiTokens call below (a token owner is both contracts).
        resolved = user
        if isinstance(resolved, Authenticatable) and resolved.is_suspended:
            return None

        await self._token_repo.touch(record)

        # Hang the token off the per-request user (Sanctum-style). Each request
        # resolves its own user object, so abilities stay request-scoped — no
        # shared state on the singleton guard. Check via user.token_can(...).
        if hasattr(user, "with_access_token"):
            user.with_access_token(record)
        return user

    async def _resolve_record(self, plain: str) -> Any | None:
        """Look up the access-token record, then verify its digest and expiry."""
        token_hash = hashlib.sha256(plain.encode()).hexdigest()
        record = await self._token_repo.find_by_hash(token_hash)
        if record is None:
            return None
        # Constant-time confirm the stored digest matches the presented one.
        # Defence-in-depth on the actual secret (the token), regardless of how
        # the repository performed its lookup.
        if not hmac.compare_digest(str(getattr(record, "token", "")), token_hash):
            return None
        if self._is_expired(record):
            return None
        return record

    @staticmethod
    def _is_expired(record: Any) -> bool:
        expires_at: Any = getattr(record, "expires_at", None)
        if expires_at is None:
            return False
        if isinstance(expires_at, datetime):
            now = datetime.now(tz=UTC)
            exp = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)
            return exp <= now
        return False

    @staticmethod
    def _extract_bearer(request: Any) -> str | None:
        headers = getattr(request, "headers", {})
        try:
            items = dict(headers)
        except TypeError, ValueError:
            return None
        lower = {str(k).lower(): str(v) for k, v in items.items()}
        raw = lower.get("authorization", "")
        if not raw.lower().startswith("bearer "):
            return None
        return raw[7:].strip() or None
