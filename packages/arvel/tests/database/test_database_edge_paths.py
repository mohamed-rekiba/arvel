"""Edge and guard paths across the database package.

These exercise the small error/empty/None branches that the happy-path suites
skip: empty collections, unknown lifecycle events, scope descriptor access,
the after-commit queue, and pagination request fallbacks.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import pytest
from arvel.database import Model, QueryBuilder, id_, string
from arvel.database import factories as factories_mod
from arvel.database.attributes import Attribute
from arvel.database.collection import ModelCollection
from arvel.database.events import (
    Observer,
    clear_observers,
    events_suppressed,
    fire_after_commit,
    fire_async,
    fire_cancellable,
    observe,
)
from arvel.database.factories import Factory
from arvel.database.orm.morph_map import morph_map_required
from arvel.database.paginator import (
    PaginationRequest,
    _page_window,  # pyright: ignore[reportPrivateUsage]  # white-box: page-window math
    reset_pagination_request,
    resolve_page,
    set_pagination_request,
)
from arvel.database.scope import SoftDeleteScope, scope
from arvel.database.seeders import Seeder
from arvel.database.session import (
    enqueue_after_commit,
    get_after_commit_queue,
    reset_after_commit_queue,
    set_after_commit_queue,
)
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class EdgeScoped(Model):
    __tablename__ = "edge_scoped"
    id: int = id_()
    status: str = string(20)

    @scope
    @staticmethod
    def active(qb: QueryBuilder[EdgeScoped]) -> QueryBuilder[EdgeScoped]:
        return qb.where(EdgeScoped.status == "active")


# ── lifecycle events ─────────────────────────────────────────────────────────


def test_events_not_suppressed_by_default() -> None:
    assert events_suppressed() is False


async def test_fire_cancellable_rejects_unknown_event() -> None:
    with pytest.raises(ValueError, match="only supports"):
        await fire_cancellable(EdgeScoped, "bogus", EdgeScoped(status="x"))


async def test_observe_then_fire_runs_callback() -> None:
    seen: list[Any] = []

    class _Obs(Observer[EdgeScoped]):
        async def created(self, instance: Any) -> None:
            seen.append(instance)

    inst = EdgeScoped(status="x")
    observe(EdgeScoped, _Obs())
    try:
        await fire_async(EdgeScoped, "created", inst)
        assert seen == [inst]
    finally:
        clear_observers(EdgeScoped)


async def test_fire_after_commit_enqueues_and_runs() -> None:
    ran: list[Any] = []

    class _Obs(Observer[EdgeScoped]):
        async def after_commit(self, instance: Any) -> None:
            ran.append(instance)

    class _Plain(Observer[EdgeScoped]):
        """No after_commit hook — exercises the skip branch in the dispatch loop."""

    inst = EdgeScoped(status="x")
    clear_observers(EdgeScoped)
    observe(EdgeScoped, _Plain())
    observe(EdgeScoped, _Obs())
    token = set_after_commit_queue([])
    try:
        fire_after_commit(EdgeScoped, inst)
        queue = get_after_commit_queue()
        assert queue is not None
        assert len(queue) == 1
        for cb in queue:
            await cb()
        assert ran == [inst]
    finally:
        reset_after_commit_queue(token)
        clear_observers(EdgeScoped)


async def test_enqueue_after_commit_outside_transaction_raises() -> None:
    async def _cb() -> None:
        return None

    with pytest.raises(RuntimeError, match="outside a DB.transaction"):
        enqueue_after_commit(_cb)


# ── collection guards ─────────────────────────────────────────────────────────


async def test_load_on_empty_collection_is_noop() -> None:
    empty: ModelCollection[Any] = ModelCollection()
    assert await empty.load("anything") is empty


async def test_load_missing_on_empty_collection_raises() -> None:
    with pytest.raises(ValueError, match="empty collection"):
        await ModelCollection().load_missing("anything")


async def test_fresh_on_empty_collection_returns_empty() -> None:
    empty: ModelCollection[Any] = ModelCollection()
    result = await empty.fresh()
    assert list(result) == []


# ── pagination fallbacks ───────────────────────────────────────────────────────


def test_resolve_page_defaults_when_param_absent() -> None:
    token = set_pagination_request(PaginationRequest(path="/", query={}))
    try:
        assert resolve_page() == 1
    finally:
        reset_pagination_request(token)


def test_resolve_page_defaults_on_non_integer() -> None:
    token = set_pagination_request(PaginationRequest(path="/", query={"page": "abc"}))
    try:
        assert resolve_page() == 1
    finally:
        reset_pagination_request(token)


def test_page_window_single_page() -> None:
    assert _page_window(1, 1, 3) == [1]


# ── scopes ─────────────────────────────────────────────────────────────────────


def test_class_scope_accepts_explicit_query_builder() -> None:
    qb = EdgeScoped.query()
    # The typed view of a @scope drops the QB param (it's auto-injected). At
    # runtime the class-level caller still forwards an explicit QB, so cast to
    # the concrete signature to exercise that branch.
    active = cast(
        "Callable[[QueryBuilder[EdgeScoped]], QueryBuilder[EdgeScoped]]", EdgeScoped.active
    )
    assert isinstance(active(qb), QueryBuilder)


def test_scope_descriptor_instance_access_binds() -> None:
    inst = EdgeScoped(status="x")
    assert callable(inst.active)


def test_scope_descriptor_get_without_owner_returns_self() -> None:
    descriptor = EdgeScoped.__dict__["active"]
    assert descriptor.__get__(EdgeScoped(status="x"), None) is descriptor


def test_soft_delete_scope_noop_when_column_absent() -> None:
    qb = EdgeScoped.query()
    assert SoftDeleteScope("missing_col").apply(qb) is qb


# ── misc small modules ─────────────────────────────────────────────────────────


def test_attribute_class_access_returns_descriptor() -> None:
    attr = Attribute.make(get=lambda _m: "x")
    assert attr.__get__(None, object) is attr


def test_seeder_call_returns_scheduled_seeder() -> None:
    class _S(Seeder):
        async def run(self) -> None:
            return None

    other = _S()
    assert _S().call(other) is other


def test_morph_map_required_is_boolean() -> None:
    assert isinstance(morph_map_required(), bool)


def test_as_list_wraps_single_value() -> None:
    # white-box: factory helpers have no public surface of their own.
    assert factories_mod._as_list("solo") == ["solo"]  # pyright: ignore[reportPrivateUsage]
    assert factories_mod._as_list([1, 2]) == [1, 2]  # pyright: ignore[reportPrivateUsage]


def test_back_ref_of_falls_back_to_relation_name() -> None:
    inst = EdgeScoped(status="x")
    assert factories_mod._back_ref_of(inst, "no_such_rel") == "no_such_rel"  # pyright: ignore[reportPrivateUsage]


def test_resolve_for_attr_uses_init_field_directly() -> None:
    parent = EdgeScoped(status="p")
    assert factories_mod._resolve_for_attr(EdgeScoped, "status", parent) == ("status", parent)  # pyright: ignore[reportPrivateUsage]


def test_resolve_for_attr_falls_back_for_non_dataclass() -> None:
    parent = EdgeScoped(status="p")
    # ``object`` isn't a dataclass and isn't mapped — both lookups fail and the
    # helper returns the (relation, parent) pair unchanged.
    assert factories_mod._resolve_for_attr(object, "missing", parent) == ("missing", parent)  # pyright: ignore[reportPrivateUsage]


def test_resolve_for_attr_falls_back_for_unknown_relation() -> None:
    parent = EdgeScoped(status="p")
    assert factories_mod._resolve_for_attr(EdgeScoped, "ghost", parent) == ("ghost", parent)  # pyright: ignore[reportPrivateUsage]


class _EdgeFactory(Factory[EdgeScoped]):
    model = EdgeScoped

    def definition(self) -> dict[str, Any]:
        return {"status": "x"}


async def test_factory_runs_async_after_creating_callback(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    fired: list[Any] = []

    async def _after(instance: Any, _faker: Any) -> None:
        fired.append(instance)

    await _EdgeFactory().after_creating(_after).create()
    assert len(fired) == 1
