"""WI-arvel-024 — Epic 006 Story 13: factory enhancements.

- ``has_attached`` — create related rows and link them through a M2M pivot.
- ``trashed()`` state — created row lands soft-deleted.
- ``after_creating`` / ``after_making`` receive a Faker instance.
- ``create_quietly`` — mute model events for the whole build.
- ``connection(name)`` — persist through a named DB connection.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
from arvel.database import Factory, Model, SoftDeletes, Timestamps
from arvel.database.db import DB
from arvel.database.orm import BelongsToMany
from sqlalchemy import Column, ForeignKey, Integer, String, Table, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.pool import StaticPool

wi024_role_user = Table(
    "wi024_role_user",
    Model.metadata,
    Column("user_id", Integer, ForeignKey("wi024_users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Integer, ForeignKey("wi024_roles.id", ondelete="CASCADE"), primary_key=True),
    Column("assigned_by", String(40), nullable=True),
)


class Wi024Role(Model):
    __tablename__ = "wi024_roles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(40), nullable=False)


class Wi024User(Model, Timestamps, SoftDeletes):
    __tablename__ = "wi024_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(80), nullable=False)

    roles: ClassVar[BelongsToMany[Wi024Role]] = BelongsToMany(
        Wi024Role,
        table=wi024_role_user,
        foreign_key="user_id",
        related_foreign_key="role_id",
    )


class RoleFactory(Factory[Wi024Role]):
    model = Wi024Role

    def definition(self) -> dict[str, Any]:
        return {"name": f"role-{self.seq('name')}"}


class UserFactory(Factory[Wi024User]):
    model = Wi024User

    def definition(self) -> dict[str, Any]:
        return {"name": "Ada"}


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


class TestHasAttached:
    async def test_pivot_rows_created_with_attributes(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        user = await (
            UserFactory()
            .has_attached("roles", RoleFactory(), count=2, pivot={"assigned_by": "system"})
            .create()
        )
        assert isinstance(user, Wi024User)
        roles = await user.roles.all()
        assert len(roles) == 2
        rows = (
            await session.execute(
                select(wi024_role_user.c.assigned_by).where(wi024_role_user.c.user_id == user.id)
            )
        ).all()
        assert [r[0] for r in rows] == ["system", "system"]


class TestTrashedState:
    async def test_created_row_is_soft_deleted(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        user = await UserFactory().trashed().create()
        assert isinstance(user, Wi024User)
        assert user.trashed()
        # Hidden by the default soft-delete scope, visible via with_trashed.
        assert await Wi024User.where(Wi024User.id == user.id).first() is None
        assert await Wi024User.with_trashed().where(Wi024User.id == user.id).first() is not None

    def test_trashed_requires_soft_deletes(self) -> None:
        with pytest.raises(AttributeError, match="SoftDeletes"):
            RoleFactory().trashed()


class TestFakerWiring:
    async def test_after_creating_receives_faker(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        seen: list[Any] = []
        await UserFactory().after_creating(lambda _m, faker: seen.append(faker)).create()
        assert len(seen) == 1
        # Faker is a dev dependency — present in tests, so it's a real instance.
        assert seen[0] is not None
        assert hasattr(seen[0], "name")

    async def test_after_making_receives_faker(self) -> None:
        seen: list[Any] = []
        UserFactory().after_making(lambda _m, faker: seen.append(faker)).make()
        assert len(seen) == 1
        assert seen[0] is not None


class TestCreateQuietly:
    async def test_create_quietly_returns_persisted_row(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        user = await UserFactory().create_quietly()
        assert isinstance(user, Wi024User)
        assert user.id is not None


class TestConnectionSelection:
    async def test_create_routes_to_named_connection(self) -> None:
        alt_engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        try:
            await _setup(alt_engine)
            maker = async_sessionmaker(alt_engine, expire_on_commit=False)
            DB.configure_named("wi024_alt", maker)
            user = await UserFactory().connection("wi024_alt").create()
            assert isinstance(user, Wi024User)
            async with maker() as s:
                found = (
                    await s.execute(select(Wi024User).where(Wi024User.id == user.id))
                ).scalar_one_or_none()
                assert found is not None
        finally:
            DB.forget_named("wi024_alt")
            await alt_engine.dispose()
