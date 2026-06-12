"""Redis session store."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from arvel.session.cipher import SessionCipher


class RedisSessionStore:
    """Session store backed by Redis."""

    def __init__(
        self,
        redis: Any = None,
        client: Any = None,
        prefix: str = "session:",
        lifetime: int = 7200,
        *,
        cipher: SessionCipher | None = None,
    ) -> None:
        self._client = redis if redis is not None else client
        self._prefix = prefix
        self._lifetime = lifetime
        self._cipher = cipher

    def _key(self, session_id: str) -> str:
        return f"{self._prefix}{session_id}"

    async def read(self, session_id: str) -> dict[str, Any]:
        raw = await self._client.get(self._key(session_id))
        if raw is None:
            return {}
        # redis-py returns bytes unless the client sets decode_responses=True;
        # the cipher token is text and json.loads is happier with str.
        payload = raw.decode() if isinstance(raw, bytes) else raw
        try:
            if self._cipher is not None:
                return self._cipher.decrypt(payload)
            parsed: Any = json.loads(payload)
            return cast("dict[str, Any]", parsed) if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, ValueError, TypeError):
            return {}

    async def write(self, session_id: str, data: dict[str, Any], lifetime: int) -> None:
        payload = self._cipher.encrypt(data) if self._cipher is not None else json.dumps(data)
        await self._client.setex(self._key(session_id), lifetime, payload)

    async def destroy(self, session_id: str) -> None:
        await self._client.delete(self._key(session_id))

    async def gc(self, max_lifetime: int) -> int:
        # Redis handles TTL-based expiry automatically.
        return 0


__all__ = ["RedisSessionStore"]
