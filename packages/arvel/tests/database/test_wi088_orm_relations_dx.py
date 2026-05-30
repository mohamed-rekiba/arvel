"""WI-arvel-088 — ORM Relations DX: immediate cleanup (Stories 4, 5, 6, 7).

RED state: all tests fail until implementation is complete.

FR-001  has_many_attr declarator replaces has_many
FR-002  Declarator implementation lives in orm/relations.py only
FR-003  Declarator-generated relationships use lazy="raise_on_sql"
FR-004  QueryLog.assert_max_queries(n) context manager
"""

from __future__ import annotations

from typing import Any

import pytest
from arvel.database import Model, has_many_attr
from arvel.database.query_logging import QueryLog
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

# ─── Test models (mirrors the has_many_attr use case from the ecommerce demo) ─


class Wi088Owner(Model):
    __tablename__ = "wi088_owners"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    name: Mapped[str] = mapped_column(String(80))
    # Declared via has_many_attr — must use lazy="raise_on_sql" (FR-003)
    items: list[Any] = has_many_attr("Wi088Item", fk="owner_id")


class Wi088Item(Model):
    __tablename__ = "wi088_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    label: Mapped[str] = mapped_column(String(80))
    owner_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("wi088_owners.id"), nullable=True, default=None
    )


async def _setup(engine: AsyncEngine) -> None:
    from arvel.database.model import Model as BaseModel

    async with engine.begin() as conn:
        await conn.run_sync(BaseModel.metadata.create_all)


# ─── FR-001: has_many_attr importable from arvel.database ─────────────────────


class TestFR001HasManyAttrImport:
    def test_has_many_attr_importable_from_arvel_database(self) -> None:
        """has_many_attr must be importable from the top-level package."""
        from arvel.database import has_many_attr

        assert callable(has_many_attr)

    def test_has_many_no_longer_in_arvel_database_all(self) -> None:
        """has_many (the declarator) must be removed from arvel.database.__all__."""
        import arvel.database as db_mod

        assert "has_many" not in db_mod.__all__, (
            "'has_many' should be removed from arvel.database.__all__; use has_many_attr instead"
        )

    def test_has_many_attr_in_arvel_database_all(self) -> None:
        """has_many_attr must be in arvel.database.__all__."""
        import arvel.database as db_mod

        assert "has_many_attr" in db_mod.__all__


# ─── FR-002: Implementation in orm/relations.py, not orm/__init__.py ──────────


class TestFR002PlacementGuard:
    def test_has_many_attr_defined_in_orm_relations(self) -> None:
        """has_many_attr must be defined in orm/relations, not orm/__init__."""
        import arvel.database.orm as orm_mod
        import arvel.database.orm.relations as relations_mod

        # Must exist in relations.py
        assert hasattr(relations_mod, "has_many_attr"), (
            "has_many_attr must be defined in arvel.database.orm.relations"
        )
        # The function in orm/__init__ must be the same object imported from relations
        assert getattr(orm_mod, "has_many_attr", None) is relations_mod.has_many_attr, (
            "orm/__init__.py must re-export has_many_attr from orm/relations, not define it"
        )

    def test_orm_init_contains_no_function_implementations(self) -> None:
        """orm/__init__.py must not contain any function definitions (re-exports only)."""
        import ast
        import inspect
        from pathlib import Path

        import arvel.database.orm as orm_mod

        src_file = inspect.getfile(orm_mod)
        tree = ast.parse(Path(src_file).read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                pytest.fail(
                    f"orm/__init__.py contains a function definition: {node.name}. "
                    "It must be a re-export hub only."
                )


# ─── FR-003: lazy="raise_on_sql" on declarator-generated relationships ─────────


class TestFR003LazyRaise:
    async def test_unloaded_relation_raises_on_access(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        """Accessing an unloaded has_many_attr attribute must raise, not lazy-load."""
        import sqlalchemy.exc

        await _setup(engine)
        owner = await Wi088Owner.create(name="Lazy Trap")
        await Wi088Item.create(label="item1", owner_id=owner.id)

        # Fetch the owner without eager loading
        fresh_owner = await Wi088Owner.find(owner.id)
        assert fresh_owner is not None

        # Accessing a has_many_attr-declared attribute without with_() must raise
        # This test requires that the attribute be declared via has_many_attr with
        # lazy="raise_on_sql". The Wi088Owner.items attribute is set up by the
        # test fixture below.
        with pytest.raises((sqlalchemy.exc.InvalidRequestError, AttributeError)):
            # Trigger access — must not silently lazy-load
            _ = fresh_owner.items

    async def test_loaded_relation_accessible_after_with(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        """After with_('items'), the attribute must be accessible without raising."""
        await _setup(engine)
        owner = await Wi088Owner.create(name="Eager OK")
        await Wi088Item.create(label="x", owner_id=owner.id)

        owners = await Wi088Owner.with_("items").all()
        assert len(owners) == 1
        # Must not raise
        items = owners[0].items
        assert len(items) == 1


# ─── FR-004: QueryLog.assert_max_queries ─────────────────────────────────────


class TestFR004AssertMaxQueries:
    async def test_passes_when_query_count_within_limit(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        """assert_max_queries should not raise when count <= n."""
        await _setup(engine)
        await Wi088Owner.create(name="q1")

        with QueryLog.assert_max_queries(5) as log:
            await Wi088Owner.all()

        assert len(log.queries) <= 5

    async def test_fails_when_query_count_exceeds_limit(
        self, engine: AsyncEngine, session: AsyncSession
    ) -> None:
        """assert_max_queries must raise AssertionError when count > n."""
        await _setup(engine)
        for i in range(3):
            await Wi088Owner.create(name=f"o{i}")

        with pytest.raises(AssertionError, match="queries"), QueryLog.assert_max_queries(0):
            await Wi088Owner.all()

    def test_assert_max_queries_is_static_contextmanager(self) -> None:
        """assert_max_queries must exist as a static method on QueryLog."""
        assert hasattr(QueryLog, "assert_max_queries"), "QueryLog.assert_max_queries must exist"

        # Must be a context manager factory
        cm = QueryLog.assert_max_queries(10)
        assert hasattr(cm, "__enter__") or hasattr(cm, "__aenter__"), (
            "QueryLog.assert_max_queries(n) must return a context manager"
        )
