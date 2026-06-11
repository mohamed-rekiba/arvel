"""End-to-end wiring for the token guard: _build_guard + concrete repositories.

Covers the path the fakes in test_token_guard.py skip — real DB-backed
ArventTokenRepository / MorphUserRepository against in-memory SQLite, and
AuthServiceProvider._build_guard producing a functional TokenGuard.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import MagicMock

from arvel.auth.config import GuardConfig
from arvel.auth.guards.token import TokenGuard
from arvel.auth.mixins import HasApiTokens
from arvel.auth.provider import AuthServiceProvider
from arvel.auth.repositories import ArventTokenRepository, MorphUserRepository
from arvel.database.columns import field
from arvel.database.model import Model
from arvel.database.session import use_session
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class TokenUser(Model, HasApiTokens):
    __tablename__ = "token_guard_wiring_users"
    __fillable__: ClassVar[list[str] | None] = ["id", "email"]

    id: str = field(length=36, primary_key=True)
    email: str = field(length=255, default="")


def _bearer(token: str) -> SimpleNamespace:
    return SimpleNamespace(headers={"authorization": f"Bearer {token}"})


async def _sqlite_session() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def test_build_guard_returns_token_guard() -> None:
    provider = AuthServiceProvider(MagicMock())
    guard = provider._build_guard(GuardConfig(driver="token", provider="users"), MagicMock())  # pyright: ignore[reportPrivateUsage]
    assert isinstance(guard, TokenGuard)


async def test_token_guard_authenticates_persisted_token() -> None:
    engine, factory = await _sqlite_session()
    try:
        async with factory() as session, use_session(session):
            user = await TokenUser.create(id="u1", email="a@b.co")
            plain = await user.create_token("cli", abilities=["*"])
            await session.commit()

            provider = AuthServiceProvider(MagicMock())
            guard = provider._build_guard(  # pyright: ignore[reportPrivateUsage]
                GuardConfig(driver="token", provider="users"), MagicMock()
            )
            assert isinstance(guard, TokenGuard)
            resolved = await guard.user(_bearer(plain))

            assert resolved is not None
            assert resolved.id == "u1"
            # Token rides on the resolved user; abilities are request-scoped.
            assert resolved.current_access_token() is not None
            assert resolved.token_can("anything") is True  # minted with ["*"]
    finally:
        await engine.dispose()


async def test_token_guard_rejects_unknown_token() -> None:
    engine, factory = await _sqlite_session()
    try:
        async with factory() as session, use_session(session):
            guard = TokenGuard(
                token_repository=ArventTokenRepository(),
                user_repository=MorphUserRepository(),
            )
            assert await guard.user(_bearer("nope")) is None
    finally:
        await engine.dispose()


async def test_repository_touch_updates_last_used_at() -> None:
    engine, factory = await _sqlite_session()
    try:
        async with factory() as session, use_session(session):
            user = await TokenUser.create(id="u2", email="b@b.co")
            plain = await user.create_token("cli")
            await session.commit()

            repo = ArventTokenRepository()
            from hashlib import sha256

            record = await repo.find_by_hash(sha256(plain.encode()).hexdigest())
            assert record is not None and record.last_used_at is None
            await repo.touch(record)
            assert record.last_used_at is not None
    finally:
        await engine.dispose()


def test_morph_repository_resolves_top_level_model() -> None:
    repo = MorphUserRepository()
    fqn = f"{TokenUser.__module__}.{TokenUser.__qualname__}"
    assert repo._resolve_model(fqn) is TokenUser  # pyright: ignore[reportPrivateUsage]
    assert repo._resolve_model("no.such.module.Thing") is None  # pyright: ignore[reportPrivateUsage]
