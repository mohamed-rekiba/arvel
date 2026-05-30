"""Eloquent-parity (backlog 005, S5 + S6): LIKE helpers, multi-column WHERE, join completeness."""

from __future__ import annotations

from arvel.database import Model
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


class Person(Model):
    __tablename__ = "lj_people"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    first: Mapped[str] = mapped_column(String(40), default="")
    last: Mapped[str] = mapped_column(String(40), default="")
    city: Mapped[str] = mapped_column(String(40), default="")


class Pet(Model):
    __tablename__ = "lj_pets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    owner_id: Mapped[int] = mapped_column(ForeignKey("lj_people.id"), default=0)
    species: Mapped[str] = mapped_column(String(20), default="")


async def _seed(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)
    await Person.create(first="Alice", last="Adams", city="Austin")
    await Person.create(first="Bob", last="Brown", city="Boston")
    await Person.create(first="alan", last="Atwood", city="Austin")
    await Pet.create(owner_id=1, species="cat")
    await Pet.create(owner_id=2, species="dog")


# ── S5: LIKE + multi-column ──────────────────────────────────────────────────


async def test_where_like_case_insensitive(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    rows = await Person.where_like("first", "al%").order_by("id").all()
    assert {r.first for r in rows} == {"Alice", "alan"}


async def test_where_like_case_sensitive_uses_plain_like(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    await _seed(engine)
    # SQLite LIKE is case-insensitive for ASCII by design, so assert the SQL form:
    # case_sensitive -> plain LIKE; default -> ILIKE (lower() folding under the generic dialect).
    cs_sql = Person.where_like("first", "al%", case_sensitive=True).to_sql().lower()
    ci_sql = Person.where_like("first", "al%").to_sql().lower()
    assert "like" in cs_sql and "lower(" not in cs_sql
    assert "lower(" in ci_sql


async def test_where_not_like(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    rows = await Person.where_not_like("first", "al%").all()
    assert [r.first for r in rows] == ["Bob"]


async def test_or_where_like_composes(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    rows = await Person.where(city="Boston").or_where_like("first", "ali%").order_by("id").all()
    assert {r.first for r in rows} == {"Bob", "Alice"}


async def test_where_all(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    # both first and last start with 'A' (case-insensitive)
    rows = await Person.where_all(["first", "last"], "ilike", "a%").order_by("id").all()
    assert {r.first for r in rows} == {"Alice", "alan"}


async def test_where_none(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    # neither first nor last starts with 'A' -> only Bob
    rows = await Person.where_none(["first", "last"], "ilike", "a%").all()
    assert [r.first for r in rows] == ["Bob"]


# ── S6: joins ────────────────────────────────────────────────────────────────


async def test_join_on_closure(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    rows = await (
        Person.join_on(Pet, lambda j: j.on(Pet.owner_id == Person.id))
        .where(Pet.species == "cat")
        .all()
    )
    assert [r.first for r in rows] == ["Alice"]


async def test_join_on_or_on(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    rows = await (
        Person.join_on(
            Pet,
            lambda j: j.on(Pet.owner_id == Person.id).or_on(Pet.species == "nope"),
        )
        .order_by("id")
        .all()
    )
    assert [r.first for r in rows] == ["Alice", "Bob"]


async def test_cross_join(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    # 3 people x 2 pets = 6 rows
    count = await Person.cross_join(Pet).count()
    assert count == 6


async def test_right_join(engine: AsyncEngine, session: AsyncSession) -> None:
    await _seed(engine)
    # right join keeps all pets (both have owners here)
    rows = await Person.right_join(Pet, Pet.owner_id == Person.id).all()
    assert len(rows) == 2
