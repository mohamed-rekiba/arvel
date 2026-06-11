"""Concrete repositories backing the token (Sanctum-style) guard.

The token guard depends on two protocols (``TokenRepository`` and
``UserRepository`` in ``arvel.auth.guards.token``). These are the production
implementations, backed by the ``PersonalAccessToken`` model and the active
ORM session. They're instantiated directly by ``AuthServiceProvider`` when a
guard uses ``driver: token``.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime
from typing import Any

from arvel.auth.models.personal_access_token import PersonalAccessToken


class ArventTokenRepository:
    """Looks up and updates ``PersonalAccessToken`` rows via the active session."""

    async def find_by_hash(self, token_hash: str) -> PersonalAccessToken | None:
        return await PersonalAccessToken.first_where(token=token_hash)

    async def touch(self, token: Any) -> None:
        token.last_used_at = datetime.now(tz=UTC)
        await token.save()


class MorphUserRepository:
    """Resolves a token's owner from its polymorphic ``(type, id)``.

    ``tokenable_type`` is the fully-qualified ``module.ClassName`` of the owning
    model (set by ``HasApiTokens.create_token``). Only top-level model classes
    are resolvable — nested classes can't round-trip through an import.
    """

    async def find(self, type_: str, id_: str) -> Any | None:
        model = self._resolve_model(type_)
        if model is None:
            return None
        return await model.find(id_)

    @staticmethod
    def _resolve_model(type_: str) -> type[Any] | None:
        module_path, _, class_name = type_.rpartition(".")
        if not module_path:
            return None
        try:
            module = importlib.import_module(module_path)
        except ImportError:
            return None
        candidate = getattr(module, class_name, None)
        return candidate if isinstance(candidate, type) else None


__all__ = ["ArventTokenRepository", "MorphUserRepository"]
