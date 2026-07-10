"""DR-0057 Fix 1 — a resource route emits no ``:int`` converter, so an int-key route param
reaches ``resolve_route_binding``/``resolve_child_route_binding`` as a raw string. SQLite accepts
``WHERE id = '5'`` (loose typing); Postgres rejects it (``bigint = varchar``) — a 500 that this
coercion prevents by turning the value into a real ``int`` before the query runs. Coercion is
int-only: string/UUID/slug keys pass through untouched (widening it would regress a
string-stored UUID column)."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.database import ConnectionResolver, HasUuids, Model


class CoercedPost(Model):
    __fields__ = {"title": str}
    __fillable__ = ["title"]


class UuidPost(Model, HasUuids):
    __fields__ = {"title": str}
    __fillable__ = ["title"]


class CoercedUser(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]

    def child_posts(self) -> object:
        return self.has_many(ChildPost, foreign_key="user_id")


class ChildPost(Model):
    __fields__ = {"title": str, "user_id": int}
    __fillable__ = ["title", "user_id"]


async def _setup(*models: type[Model]) -> ConnectionResolver:
    db = ConnectionResolver()
    for model in models:
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    return db


def test_coerce_route_key_turns_a_string_into_a_real_int() -> None:
    # the Postgres-shaped proof: the bound value is an actual int, not a str the driver
    # would compare against a bigint column and reject.
    coerced = CoercedPost._coerce_route_key("id", "5")
    assert coerced == 5
    assert isinstance(coerced, int)


def test_coerce_route_key_is_a_noop_for_string_columns() -> None:
    assert UuidPost._coerce_route_key("id", "some-string-value") == "some-string-value"


async def test_int_pk_model_resolves_a_string_route_value() -> None:
    db = await _setup(CoercedPost)
    try:
        post = await CoercedPost.create(title="hi")
        found = await CoercedPost.resolve_route_binding(str(post.id))
        assert found is not None
        assert found.id == post.id
    finally:
        await db.dispose()


async def test_garbage_id_is_a_clean_miss_not_an_error() -> None:
    db = await _setup(CoercedPost)
    try:
        await CoercedPost.create(title="hi")
        found = await CoercedPost.resolve_route_binding("abc")
        assert found is None  # -> BindingMissing -> 404, never a 500 / driver error
    finally:
        await db.dispose()


async def test_already_int_value_is_a_noop() -> None:
    db = await _setup(CoercedPost)
    try:
        post = await CoercedPost.create(title="hi")
        found = await CoercedPost.resolve_route_binding(post.id)  # already int
        assert found is not None and found.id == post.id
    finally:
        await db.dispose()


async def test_string_pk_model_still_binds_by_its_native_key() -> None:
    db = await _setup(UuidPost)
    try:
        post = await UuidPost.create(title="hi")
        found = await UuidPost.resolve_route_binding(post.id)  # str uuid, unchanged
        assert found is not None and found.id == post.id
    finally:
        await db.dispose()


async def test_scoped_child_route_resolves_int_id_and_still_404s_cross_parent() -> None:
    db = await _setup(CoercedUser, ChildPost)
    try:
        ada = await CoercedUser.create(name="Ada")
        bob = await CoercedUser.create(name="Bob")
        adas_post = await ChildPost.create(title="mine", user_id=ada.id)

        # a valid int-string child id, scoped to its real parent, resolves.
        resolved = await ChildPost.resolve_child_route_binding(ada, str(adas_post.id))
        assert resolved is not None and resolved.id == adas_post.id

        # the same child, scoped to the wrong parent, still 404s (K4/DR-0053 preserved).
        missing = await ChildPost.resolve_child_route_binding(bob, str(adas_post.id))
        assert missing is None
    finally:
        await db.dispose()


async def test_with_trashed_still_resolves_a_soft_deleted_row_by_int_key() -> None:
    from arvel.database import SoftDeletes

    class TrashablePost(Model, SoftDeletes):
        __fields__ = {"title": str}
        __fillable__ = ["title"]

    db = await _setup(TrashablePost)
    try:
        post = await TrashablePost.create(title="hi")
        await post.delete()
        found = await TrashablePost.resolve_route_binding(str(post.id), with_trashed=True)
        assert found is not None and found.id == post.id
    finally:
        await db.dispose()
