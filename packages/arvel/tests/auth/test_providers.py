"""
DatabaseUserProvider + Authenticatable + HasApiTokens mixins.
"""

from __future__ import annotations

from typing import Any

import pytest
from arvel.database import Model, id_, string


class _UserA(Model):
    __tablename__ = "auth_test_users_a"
    id: int = id_()
    email: str = string(255, unique=True)
    password_hash: str = string(255)


class _UserB(Model):
    __tablename__ = "auth_test_users_b"
    id: int = id_()
    email: str = string(255)
    password_hash: str = string(255)


class _UserC(Model):
    __tablename__ = "auth_test_users_c"
    id: int = id_()
    email: str = string(255, unique=True)
    password_hash: str = string(255)


# DatabaseUserProvider.by_id


@pytest.mark.asyncio
async def test_database_provider_by_id_returns_model_instance(engine: Any, session: Any) -> None:
    from arvel.auth.providers.database import DatabaseUserProvider

    async with engine.begin() as conn:
        await conn.run_sync(_UserA.metadata.create_all)

    u = _UserA(email="a@example.com", password_hash="hashed")
    session.add(u)
    await session.flush()

    provider = DatabaseUserProvider(model=_UserA)
    found = await provider.by_id(str(u.id))
    assert found is not None
    assert found.email == "a@example.com"


@pytest.mark.asyncio
async def test_database_provider_by_id_returns_none_for_missing_id(
    engine: Any, session: Any
) -> None:
    from arvel.auth.providers.database import DatabaseUserProvider

    async with engine.begin() as conn:
        await conn.run_sync(_UserB.metadata.create_all)

    provider = DatabaseUserProvider(model=_UserB)
    result = await provider.by_id("99999")
    assert result is None


# DatabaseUserProvider.by_credentials


@pytest.mark.asyncio
async def test_database_provider_by_credentials_finds_by_email(engine: Any, session: Any) -> None:
    from arvel.auth.providers.database import DatabaseUserProvider

    async with engine.begin() as conn:
        await conn.run_sync(_UserC.metadata.create_all)

    u = _UserC(email="b@example.com", password_hash="h")
    session.add(u)
    await session.flush()

    provider = DatabaseUserProvider(model=_UserC, username_field="email")
    found = await provider.by_credentials({"email": "b@example.com"})
    assert found is not None
    assert found.email == "b@example.com"


# Authenticatable mixin


def test_authenticatable_mixin_exposes_get_auth_id() -> None:
    from arvel.auth.mixins import Authenticatable

    class User(Authenticatable):
        id = 42

    u = User()
    assert u.get_auth_id() == "42"


def test_authenticatable_mixin_exposes_get_auth_password() -> None:
    from arvel.auth.mixins import Authenticatable

    class User(Authenticatable):
        password_hash = "bcrypt_hashed"

    u = User()
    assert u.get_auth_password() == "bcrypt_hashed"


def test_authenticatable_mixin_password_field_is_configurable() -> None:
    from arvel.auth.mixins import Authenticatable

    class User(Authenticatable):
        _auth_password_field = "hashed_password"
        hashed_password = "custom_field"

    u = User()
    assert u.get_auth_password() == "custom_field"


# HasApiTokens mixin


def test_has_api_tokens_mixin_create_token_returns_plain_text_once() -> None:
    from arvel.auth.mixins import HasApiTokens

    class User(HasApiTokens):
        id = 1
        token_records: list[Any] = []

        def _persist_token(self, record: Any) -> Any:
            self.token_records.append(record)
            return record

    u = User()
    plain_token = u.create_token_sync("my-token", abilities=["*"])

    assert isinstance(plain_token, str)
    assert len(plain_token) > 0
    assert len(u.token_records) == 1
    import hashlib

    assert u.token_records[0].token == hashlib.sha256(plain_token.encode()).hexdigest()


def test_has_api_tokens_plain_token_is_not_the_stored_hash() -> None:
    import hashlib

    from arvel.auth.mixins import HasApiTokens

    class User(HasApiTokens):
        id = 1
        token_records: list[Any] = []

        def _persist_token(self, record: Any) -> Any:
            self.token_records.append(record)
            return record

    u = User()
    plain = u.create_token_sync("tok", abilities=["read"])
    assert plain != u.token_records[0].token
    assert u.token_records[0].token == hashlib.sha256(plain.encode()).hexdigest()
