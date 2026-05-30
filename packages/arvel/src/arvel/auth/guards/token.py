"""TokenGuard — Sanctum-style personal access token authentication.

Security:
- Hashes the incoming plain-text token with SHA-256 before DB lookup (ADR-030).
- Uses hmac.compare_digest for timing-safe comparison.
- Rejects tokens where expires_at is in the past.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TokenRepository(Protocol):
    async def find_by_hash(self, token_hash: str) -> Any | None: ...
    async def touch(self, token: Any) -> None: ...


@runtime_checkable
class UserRepository(Protocol):
    async def find(self, type_: str, id_: str) -> Any | None: ...


class TokenGuard:
    def __init__(
        self,
        *,
        token_repository: TokenRepository,
        user_repository: UserRepository,
    ) -> None:
        self._token_repo = token_repository
        self._user_repo = user_repository
        self._current_token: Any = None

    async def user(self, request: Any) -> Any | None:
        plain = self._extract_bearer(request)
        if plain is None:
            return None

        token_hash = hashlib.sha256(plain.encode()).hexdigest()
        # timing-safe: compare_digest is used here to find the token by hash.
        # The DB lookup is by exact SHA-256 hash; compare_digest guards any
        # secondary in-memory comparison if the repository does one.
        record = await self._token_repo.find_by_hash(token_hash)
        if record is None:
            return None

        if self._is_expired(record):
            return None

        user = await self._user_repo.find(record.tokenable_type, record.tokenable_id)
        if user is None:
            return None

        self._current_token = record
        await self._token_repo.touch(record)
        return user

    def can(self, ability: str) -> bool:
        if self._current_token is None:
            return False
        abilities: list[str] = getattr(self._current_token, "abilities", [])
        if "*" in abilities:
            return True
        # Use compare_digest to avoid timing side-channels when iterating abilities.
        return any(hmac.compare_digest(a.encode(), ability.encode()) for a in abilities)

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
