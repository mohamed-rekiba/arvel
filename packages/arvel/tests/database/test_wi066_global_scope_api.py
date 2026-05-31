"""WI-arvel-066 — Epic 049 Story 2: programmatic global-scope API.

Three things land here:

* ``Model.add_global_scope(name, scope)`` — register a global scope at runtime
  (callable or :class:`GlobalScope` instance), without editing
  ``__arvel_global_scopes__`` by hand.
* ``SoftDeleteScope`` — the soft-delete default scope as a real
  :class:`GlobalScope` subclass, exposed publicly. The :class:`SoftDeletes`
  mixin registers an instance of it.
* Subclass inheritance — a global scope registered on a parent must apply
  to subclass queries, and registering on the subclass must not mutate the
  parent's scope dict.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from arvel.database import Model, QueryBuilder, SoftDeletes, id_, string
from arvel.database.scope import GlobalScope, SoftDeleteScope
from sqlalchemy.ext.asyncio import AsyncSession


class _Tenant(Model):
    __tablename__ = "tenants_wi066"
    id: int = id_()
    tenant_id: str = string(40, default="t1")
    name: str = string(40, default="x")


async def _setup(engine: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


def _clear_global_scopes(cls: type) -> None:
    # Isolate tests — modules can run in any order, and these scopes mutate
    # class state.
    if "__arvel_global_scopes__" in cls.__dict__:
        cls_any: Any = cls
        cls_any.__arvel_global_scopes__ = {}


# ---------------------------------------------------------------------------
# add_global_scope — callable form
# ---------------------------------------------------------------------------


class TestAddGlobalScopeCallable:
    async def test_lambda_applies_to_all_queries(self, engine: Any, session: AsyncSession) -> None:
        _clear_global_scopes(_Tenant)
        await _setup(engine)
        await _Tenant.create(tenant_id="t1", name="a")
        await _Tenant.create(tenant_id="t2", name="b")

        def _only_t1(qb: QueryBuilder[Any]) -> QueryBuilder[Any]:
            return qb.where(_Tenant.__table__.c.tenant_id == "t1")

        _Tenant.add_global_scope("tenant_filter", _only_t1)

        rows = await _Tenant.all()
        assert [r.name for r in rows] == ["a"]
        _clear_global_scopes(_Tenant)

    async def test_without_global_scope_removes_named(
        self, engine: Any, session: AsyncSession
    ) -> None:
        _clear_global_scopes(_Tenant)
        await _setup(engine)
        await _Tenant.create(tenant_id="t1", name="a")
        await _Tenant.create(tenant_id="t2", name="b")

        def _only_t1(qb: QueryBuilder[Any]) -> QueryBuilder[Any]:
            return qb.where(_Tenant.__table__.c.tenant_id == "t1")

        _Tenant.add_global_scope("tenant_filter", _only_t1)

        rows = await _Tenant.query().without_global_scope("tenant_filter").all()
        assert sorted(r.name for r in rows) == ["a", "b"]
        _clear_global_scopes(_Tenant)


# ---------------------------------------------------------------------------
# add_global_scope — GlobalScope instance form
# ---------------------------------------------------------------------------


class _OnlyNamed(GlobalScope):
    def __init__(self, name: str) -> None:
        self.name = name

    def apply(self, qb: QueryBuilder[Any]) -> QueryBuilder[Any]:
        return qb.where(_Tenant.__table__.c.name == self.name)


class TestAddGlobalScopeInstance:
    async def test_global_scope_instance_applies(self, engine: Any, session: AsyncSession) -> None:
        _clear_global_scopes(_Tenant)
        await _setup(engine)
        await _Tenant.create(tenant_id="t1", name="alpha")
        await _Tenant.create(tenant_id="t1", name="beta")

        _Tenant.add_global_scope("only_alpha", _OnlyNamed("alpha"))

        rows = await _Tenant.all()
        assert [r.name for r in rows] == ["alpha"]
        _clear_global_scopes(_Tenant)


# ---------------------------------------------------------------------------
# Subclass inheritance
# ---------------------------------------------------------------------------


class _Animal(Model):
    __abstract__ = True
    species: str = string(40, default="cat")


class _Pet(_Animal):
    __tablename__ = "pets_wi066"
    id: int = id_()


class TestGlobalScopeInheritance:
    async def test_subclass_inherits_parent_scope(self, engine: Any, session: AsyncSession) -> None:
        _clear_global_scopes(_Animal)
        _clear_global_scopes(_Pet)

        def _only_cats(qb: QueryBuilder[Any]) -> QueryBuilder[Any]:
            return qb.where(_Animal.__table__.c.species == "cat")

        _Animal.add_global_scope("only_cats", _only_cats)

        scopes = getattr(_Pet, "__arvel_global_scopes__", {})
        assert "only_cats" in scopes
        _clear_global_scopes(_Animal)

    async def test_subclass_add_does_not_mutate_parent(
        self,
        engine: Any,
        session: AsyncSession,
    ) -> None:
        _clear_global_scopes(_Animal)
        _clear_global_scopes(_Pet)

        def _noop(qb: QueryBuilder[Any]) -> QueryBuilder[Any]:
            return qb

        _Animal.add_global_scope("p", _noop)
        _Pet.add_global_scope("c", _noop)

        parent_scopes = _Animal.__dict__.get("__arvel_global_scopes__", {})
        child_scopes = _Pet.__dict__.get("__arvel_global_scopes__", {})

        assert set(parent_scopes.keys()) == {"p"}
        assert set(child_scopes.keys()) == {"p", "c"}
        _clear_global_scopes(_Animal)
        _clear_global_scopes(_Pet)


# ---------------------------------------------------------------------------
# SoftDeleteScope — the named soft-delete scope
# ---------------------------------------------------------------------------


class _Note(SoftDeletes, Model):
    __tablename__ = "notes_wi066"
    id: int = id_()
    body: str = string(80, default="")


class TestSoftDeleteScope:
    def test_soft_delete_scope_is_a_global_scope_subclass(self) -> None:
        assert issubclass(SoftDeleteScope, GlobalScope)

    def test_softdeletes_registers_soft_delete_scope_instance(self) -> None:
        scopes = getattr(_Note, "__arvel_global_scopes__", {})
        assert "soft_delete" in scopes

    async def test_default_query_hides_soft_deleted(
        self, engine: Any, session: AsyncSession
    ) -> None:
        await _setup(engine)
        n1 = await _Note.create(body="a")
        await _Note.create(body="b")
        n1.deleted_at = datetime.now(UTC)
        await n1.save()

        rows = await _Note.all()
        assert [r.body for r in rows] == ["b"]

    async def test_with_trashed_bypasses_scope(self, engine: Any, session: AsyncSession) -> None:
        await _setup(engine)
        n1 = await _Note.create(body="a")
        await _Note.create(body="b")
        n1.deleted_at = datetime.now(UTC)
        await n1.save()

        rows = await _Note.query().with_trashed().all()
        assert sorted(r.body for r in rows) == ["a", "b"]


# ---------------------------------------------------------------------------
# Bad input
# ---------------------------------------------------------------------------


class TestAddGlobalScopeErrors:
    def test_rejects_non_callable(self) -> None:
        with pytest.raises(TypeError):
            _Tenant.add_global_scope("bad", 42)
