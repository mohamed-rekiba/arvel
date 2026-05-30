"""FR-003-035..037 — Factories and seeders."""

from __future__ import annotations

from typing import Any

import pytest
from arvel.database import DatabaseSeeder, Factory, Model
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column


class Person(Model):
    __tablename__ = "people_f"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class PersonFactory(Factory[Person]):
    model = Person

    def definition(self) -> dict[str, Any]:
        return {"name": "Anonymous", "age": 42}


async def _setup(engine: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def test_factory_make_returns_instance_without_db(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    person = PersonFactory().make()
    assert isinstance(person, Person)
    assert person.id is None  # not persisted yet


async def test_factory_create_persists(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    person = await PersonFactory().create()
    assert isinstance(person, Person)
    assert person.id is not None
    assert person.name == "Anonymous"


async def test_factory_count_creates_multiple(engine: Any, session: AsyncSession) -> None:
    await _setup(engine)
    people = await PersonFactory().count(3).create()
    assert isinstance(people, list)
    assert len(people) == 3
    assert all(p.id is not None for p in people)


async def test_factory_state_overrides_definition_defaults(
    engine: Any, session: AsyncSession
) -> None:
    await _setup(engine)
    person = await PersonFactory().state({"name": "Ada"}).create()
    assert isinstance(person, Person)
    assert person.name == "Ada"


async def test_seeder_blocks_in_production() -> None:
    from types import SimpleNamespace

    from arvel.config._lookup_registry import register

    register("app", SimpleNamespace(env="production", is_production=True))
    seeder = DatabaseSeeder()
    with pytest.raises(RuntimeError, match="production"):
        await seeder.run()


async def test_seeder_runs_in_non_production() -> None:
    seeder = DatabaseSeeder()
    await seeder.run()  # no-op default, should not raise
