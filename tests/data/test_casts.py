"""Tests for attribute casting and accessors/mutators."""

from __future__ import annotations

import enum
import json
from typing import TYPE_CHECKING, ClassVar

import pytest
from sqlalchemy import String, Text, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column  # noqa: TC002

from arvel.data.accessors import accessor, mutator
from arvel.data.casts import (
    BoolCaster,
    EnumCaster,
    FloatCaster,
    IntCaster,
    JsonCaster,
    resolve_caster,
)
from arvel.data.model import ArvelModel
from arvel.data.observer import ObserverRegistry
from arvel.data.repository import Repository
from arvel.data.transaction import Transaction

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


# ──── Enums ────


class UserRole(enum.Enum):
    ADMIN = "admin"
    USER = "user"
    MODERATOR = "moderator"


# ──── Models ────


class CastUser(ArvelModel):
    __tablename__ = "cast_users"
    __casts__: ClassVar[dict] = {
        "options": "json",
        "role": UserRole,
        "score": "float",
        "rank": "int",
        "is_verified": "bool",
    }

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    options: Mapped[str | None] = mapped_column(Text, default=None)
    role: Mapped[str] = mapped_column(String(20), default="user")
    score: Mapped[str | None] = mapped_column(String(20), default=None)
    rank: Mapped[str | None] = mapped_column(String(10), default=None)
    is_verified: Mapped[int] = mapped_column(default=0)


class AccessorUser(ArvelModel):
    __tablename__ = "accessor_users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    raw_password: Mapped[str | None] = mapped_column(String(255), default=None)

    @accessor("full_name")
    def get_full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @mutator("raw_password")
    def set_raw_password(self, value: str) -> str:
        return f"hashed_{value}"


# ──── Repositories / Transaction ────


class CastUserRepository(Repository[CastUser]):
    pass


class AccessorUserRepository(Repository[AccessorUser]):
    pass


class CastTransaction(Transaction):
    cast_users: CastUserRepository
    accessor_users: AccessorUserRepository


# ──── Fixtures ────


@pytest.fixture(scope="module", params=["asyncio"], autouse=True)
def anyio_backend(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture
async def cast_session() -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(ArvelModel.metadata.create_all)

    async with engine.connect() as conn:
        trans = await conn.begin()
        async with AsyncSession(bind=conn, expire_on_commit=False) as session:
            yield session
            if trans.is_active:
                await trans.rollback()

    await engine.dispose()


@pytest.fixture
def cast_tx(cast_session: AsyncSession) -> CastTransaction:
    return CastTransaction(session=cast_session, observer_registry=ObserverRegistry())


# ──── Cast resolution tests ────


class TestCastResolution:
    def test_resolve_json(self):
        caster = resolve_caster("json")
        assert isinstance(caster, JsonCaster)

    def test_resolve_bool(self):
        assert isinstance(resolve_caster("bool"), BoolCaster)

    def test_resolve_int(self):
        assert isinstance(resolve_caster("int"), IntCaster)

    def test_resolve_float(self):
        assert isinstance(resolve_caster("float"), FloatCaster)

    def test_resolve_enum(self):
        caster = resolve_caster(UserRole)
        assert isinstance(caster, EnumCaster)

    def test_resolve_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown cast type"):
            resolve_caster("nonexistent")


# ──── JSON cast tests ────


class TestJsonCast:
    def test_json_get_from_string(self):
        c = JsonCaster()
        assert c.get('{"key": "value"}', "opts", None) == {"key": "value"}

    def test_json_get_from_dict(self):
        c = JsonCaster()
        assert c.get({"key": "value"}, "opts", None) == {"key": "value"}

    def test_json_set_from_dict(self):
        c = JsonCaster()
        result = c.set({"key": "value"}, "opts", None)
        assert json.loads(result) == {"key": "value"}

    def test_json_none(self):
        c = JsonCaster()
        assert c.get(None, "opts", None) is None
        assert c.set(None, "opts", None) is None


# ──── Enum cast tests ────


class TestEnumCast:
    def test_enum_get_from_value(self):
        c = EnumCaster(UserRole)
        assert c.get("admin", "role", None) == UserRole.ADMIN

    def test_enum_get_from_member(self):
        c = EnumCaster(UserRole)
        assert c.get(UserRole.ADMIN, "role", None) == UserRole.ADMIN

    def test_enum_set_from_member(self):
        c = EnumCaster(UserRole)
        assert c.set(UserRole.ADMIN, "role", None) == "admin"

    def test_enum_none(self):
        c = EnumCaster(UserRole)
        assert c.get(None, "role", None) is None


# ──── Model-level casting via get_cast_value ────


class TestModelCasting:
    async def test_get_cast_value_json(
        self, cast_session: AsyncSession, cast_tx: CastTransaction
    ) -> None:
        async with cast_tx:
            user = await cast_tx.cast_users.create(
                {"name": "Alice", "options": '{"theme": "dark"}', "role": "admin"}
            )
            cast_val = user.get_cast_value("options")
            assert cast_val == {"theme": "dark"}

    async def test_get_cast_value_enum(
        self, cast_session: AsyncSession, cast_tx: CastTransaction
    ) -> None:
        async with cast_tx:
            user = await cast_tx.cast_users.create({"name": "Bob", "role": "admin"})
            assert user.get_cast_value("role") == UserRole.ADMIN

    async def test_get_cast_value_float(
        self, cast_session: AsyncSession, cast_tx: CastTransaction
    ) -> None:
        async with cast_tx:
            user = await cast_tx.cast_users.create({"name": "Charlie", "score": "9.5"})
            assert user.get_cast_value("score") == pytest.approx(9.5)

    async def test_get_cast_value_int(
        self, cast_session: AsyncSession, cast_tx: CastTransaction
    ) -> None:
        async with cast_tx:
            user = await cast_tx.cast_users.create({"name": "Diana", "rank": "42"})
            assert user.get_cast_value("rank") == 42

    async def test_get_cast_value_bool(
        self, cast_session: AsyncSession, cast_tx: CastTransaction
    ) -> None:
        async with cast_tx:
            user = await cast_tx.cast_users.create({"name": "Eve", "is_verified": 1})
            assert user.get_cast_value("is_verified") is True


# ──── model_dump with casts ────


class TestModelDumpWithCasts:
    async def test_model_dump_applies_casts(
        self, cast_session: AsyncSession, cast_tx: CastTransaction
    ) -> None:
        async with cast_tx:
            user = await cast_tx.cast_users.create(
                {"name": "Frank", "options": '{"a": 1}', "role": "moderator", "is_verified": 1}
            )
            dumped = user.model_dump()
            assert dumped["options"] == {"a": 1}
            assert dumped["role"] == UserRole.MODERATOR
            assert dumped["is_verified"] is True


# ──── Accessor tests ────


class TestAccessors:
    async def test_accessor_virtual_attribute(
        self, cast_session: AsyncSession, cast_tx: CastTransaction
    ) -> None:
        async with cast_tx:
            user = await cast_tx.accessor_users.create(
                {"first_name": "Alice", "last_name": "Smith"}
            )
            assert user.full_name == "Alice Smith"

    async def test_accessor_in_model_dump(
        self, cast_session: AsyncSession, cast_tx: CastTransaction
    ) -> None:
        async with cast_tx:
            user = await cast_tx.accessor_users.create({"first_name": "Bob", "last_name": "Jones"})
            dumped = user.model_dump(include={"first_name", "last_name", "full_name"})
            assert dumped["full_name"] == "Bob Jones"

    async def test_unknown_accessor_raises(
        self, cast_session: AsyncSession, cast_tx: CastTransaction
    ) -> None:
        async with cast_tx:
            user = await cast_tx.accessor_users.create(
                {"first_name": "Charlie", "last_name": "Brown"}
            )
            with pytest.raises(AttributeError, match="no attribute"):
                _ = user.nonexistent_accessor


# ──── Mutator tests ────


class TestMutators:
    async def test_mutator_transforms_on_create(
        self, cast_session: AsyncSession, cast_tx: CastTransaction
    ) -> None:
        async with cast_tx:
            user = await cast_tx.accessor_users.create(
                {"first_name": "Diana", "last_name": "Prince", "raw_password": "secret123"}
            )
            # Mutator should have transformed the value
            registry = AccessorUser.__accessor_registry__
            mut_fn = registry.get_mutator("raw_password")
            assert mut_fn is not None
            assert mut_fn(user, "secret123") == "hashed_secret123"
