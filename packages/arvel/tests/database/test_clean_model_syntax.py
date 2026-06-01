"""Clean model syntax — type-inferred columns + the generic ``field``.

Bare annotations (``name: str``), plain Python defaults (``age: int | None = None``),
and ``field(...)`` produce real SQLAlchemy columns without ``Mapped`` /
``mapped_column``, while explicit helpers keep working. These models double as
the mypy/pyright sample — the suite is type-checked under --strict."""

from __future__ import annotations

import enum
import inspect
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

from arvel.database import Model, field, json
from sqlalchemy import DateTime, Enum, Integer, Numeric, String
from sqlalchemy import inspect as sqla_inspect
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class Color(enum.StrEnum):
    red = "red"
    blue = "blue"


class Hero(Model):
    __tablename__ = "clean_heroes"

    id: int | None = field(default=None, primary_key=True)
    name: str
    secret_name: str
    age: int | None = None


class Widget(Model):
    __tablename__ = "clean_widgets"

    id: int | None = field(default=None, primary_key=True)
    title: str
    sku: str = field(length=32, unique=True, index=True)
    quantity: int = 0
    price: Decimal = Decimal("0.00")
    released_at: datetime | None = None
    color: Color = Color.red
    blob: Any = json(default=dict)


class Team(Model):
    __tablename__ = "clean_teams"

    id: int | None = field(default=None, primary_key=True)
    name: str


class Member(Model):
    __tablename__ = "clean_members"

    id: int | None = field(default=None, primary_key=True)
    name: str
    team_id: int = field(foreign_key="clean_teams.id")


async def _setup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


def _cols(model: type[Model]) -> Any:
    return sqla_inspect(model).columns


class TestInferredTypes:
    def test_bare_str_becomes_varchar_255_not_null(self) -> None:
        col = _cols(Hero)["name"]
        assert isinstance(col.type, String)
        assert col.type.length == 255
        assert col.nullable is False

    def test_optional_plain_default_is_nullable(self) -> None:
        col = _cols(Hero)["age"]
        assert isinstance(col.type, Integer)
        assert col.nullable is True

    def test_field_primary_key(self) -> None:
        assert _cols(Hero)["id"].primary_key is True

    def test_inferred_datetime_is_timezone_aware(self) -> None:
        col = _cols(Widget)["released_at"]
        assert isinstance(col.type, DateTime)
        assert col.type.timezone is True
        assert col.nullable is True

    def test_inferred_decimal_precision(self) -> None:
        numeric = cast("Numeric[Any]", _cols(Widget)["price"].type)
        assert isinstance(numeric, Numeric)
        assert numeric.precision == 10
        assert numeric.scale == 2

    def test_inferred_enum(self) -> None:
        assert isinstance(_cols(Widget)["color"].type, Enum)

    def test_field_length_unique_index(self) -> None:
        col = _cols(Widget)["sku"]
        assert isinstance(col.type, String)
        assert col.type.length == 32
        assert col.unique is True
        assert col.index is True

    def test_explicit_helper_still_works(self) -> None:
        # json keeps its mutation-tracking type; inference doesn't touch it.
        assert _cols(Widget)["blob"] is not None


class TestInitSignature:
    def test_bare_annotations_are_required(self) -> None:
        params = inspect.signature(Hero).parameters
        assert params["name"].default is inspect.Parameter.empty
        assert params["secret_name"].default is inspect.Parameter.empty

    def test_plain_default_and_pk_are_optional(self) -> None:
        params = inspect.signature(Hero).parameters
        assert params["age"].default is None
        assert params["id"].default is None


class TestRoundTrip:
    async def test_create_and_find(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        hero = await Hero.create(name="Deadpond", secret_name="Dive Wilson")
        assert hero.id is not None
        assert hero.age is None

        found = await Hero.find(hero.id)
        assert found is not None
        assert found.name == "Deadpond"
        assert found.secret_name == "Dive Wilson"

    async def test_plain_defaults_applied(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        w = await Widget.create(title="Gizmo", sku="SKU-1")
        assert w.quantity == 0
        assert w.price == Decimal("0.00")
        assert w.released_at is None
        assert w.color is Color.red
        assert w.blob == {}

    async def test_foreign_key_relation(self, engine: AsyncEngine, session: AsyncSession) -> None:
        await _setup(engine)
        team = await Team.create(name="Avengers")
        member = await Member.create(name="Tony", team_id=team.id)
        assert member.team_id == team.id
        fk_cols = _cols(Member)["team_id"].foreign_keys
        assert any(fk.column.table.name == "clean_teams" for fk in fk_cols)


class TestPlainDefaultIsolation:
    async def test_json_default_not_shared(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        await _setup(engine)
        a = await Widget.create(title="A", sku="A-1")
        b = await Widget.create(title="B", sku="B-1")
        a.blob["x"] = 1
        assert b.blob == {}
