"""OAuthAccount model — links a provider identity to a host User.

``tokens`` is encrypted at rest with the app encrypter (AES-256-GCM, keyed from
``APP_KEY``). The key is resolved lazily at bind/result time so importing the
model never requires ``APP_KEY`` to be present.
"""

from __future__ import annotations

import json
from typing import Any, cast

from arvel.database import field, nullable_column
from arvel.database.model import Model, Timestamps
from arvel.facades.crypt import Crypt
from sqlalchemy import Text, TypeDecorator, UniqueConstraint
from sqlalchemy.engine import Dialect


class EncryptedJson(TypeDecorator[dict[str, Any]]):
    """Stores a JSON dict encrypted with the app encrypter; ``None`` passes through."""

    impl = Text
    cache_ok = False

    def process_bind_param(self, value: dict[str, Any] | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return Crypt.encrypt_string(json.dumps(value))

    def process_result_value(self, value: Any, dialect: Dialect) -> dict[str, Any] | None:
        if value is None:
            return None
        decoded: object = json.loads(Crypt.decrypt_string(str(value)))
        if not isinstance(decoded, dict):
            return None
        items = cast("dict[object, object]", decoded)
        return {str(k): v for k, v in items.items()}


class OAuthAccount(Model, Timestamps):
    """A provider account linked to a host user.

    ``UNIQUE(provider, provider_id)`` guarantees one link per remote identity.
    ``provider_id`` is stored verbatim — never normalised — to avoid collisions.
    """

    __tablename__ = "oauth_accounts"
    __table_args__ = (
        UniqueConstraint("provider", "provider_id", name="oauth_accounts_provider_unique"),
    )

    id: int = field(default=None, primary_key=True, init=False)
    user_id: str = field(length=36, foreign_key="users.id", on_delete="CASCADE", index=True)
    provider: str = field(length=40)
    provider_id: str
    tokens: dict[str, Any] | None = nullable_column(EncryptedJson(), default=None)


__all__ = ["EncryptedJson", "OAuthAccount"]
