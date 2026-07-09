"""Integration (doc 20) — the ORM compiles + round-trips against a real PostgreSQL, not SQLite.

Also covers spec 08 (DB-MODEL): the new casts + the full model event lifecycle, against a real
Postgres connection (not just SQLite — Postgres has its own TEXT/DECIMAL column behavior)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest
import sqlalchemy as sa

from arvel.database import Builder, ConnectionResolver, Factory, Model
from arvel.database.collection import ModelCollection
from arvel.database.relations import SyncResult
from arvel.events import Dispatcher
from arvel.kernel import Application, set_application
from arvel.pagination import CursorPaginator
from arvel.security import Encrypter
from arvel.support import Collection, Stringable

pytestmark = pytest.mark.integration


class Gadget(Model):
    __fields__: ClassVar = {"name": str, "qty": int}
    __fillable__: ClassVar = ["name", "qty"]
    __timestamps__ = True


class RichItem(Model):
    __fields__: ClassVar = {
        "tags": list,
        "extra": dict,
        "profile": dict,
        "price": str,
        "secret": str,
        "slug": str,
    }
    __fillable__: ClassVar = list(__fields__)
    __casts__: ClassVar = {
        "tags": "array",
        "extra": "collection",
        "profile": "object",
        "price": "decimal:2",
        "secret": "encrypted:array",
        "slug": "stringable",
    }


async def test_orm_roundtrip_on_postgres(postgres_url: str) -> None:
    db = ConnectionResolver({"default": {"url": postgres_url}})
    Gadget.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(Gadget.__table__))

        a = await Gadget.create(name="widget", qty=3)
        await Gadget.create(name="sprocket", qty=10)

        found = await Gadget.find(a.id)
        assert found is not None and found.name == "widget"

        many = await Gadget.where("qty", ">", 5).get()
        assert [g.name for g in many] == ["sprocket"]

        assert await Gadget.count() == 2
    finally:
        await db.execute(sa.schema.DropTable(Gadget.__table__))
        await db.dispose()


async def test_new_casts_round_trip_on_postgres(postgres_url: str) -> None:
    app = Application()
    app.instance("encrypter", Encrypter(Encrypter.generate_key()))
    set_application(app)
    db = ConnectionResolver({"default": {"url": postgres_url}})
    RichItem.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(RichItem.__table__))

        created = await RichItem.create(
            tags=["a", "b"],
            extra=Collection([1, 2]),
            profile={"name": "Ada"},
            price=Decimal("9.995"),
            secret=[1, "two", 3],
            slug="hello",
        )
        assert created.price == Decimal("10.00")  # quantized on set (bankers' rounding)

        reloaded = await RichItem.find(created.id)
        assert reloaded is not None
        assert reloaded.tags == ["a", "b"]
        assert isinstance(reloaded.extra, Collection) and reloaded.extra.all() == [1, 2]
        assert isinstance(reloaded.profile, SimpleNamespace) and reloaded.profile.name == "Ada"
        assert isinstance(reloaded.price, Decimal) and reloaded.price == Decimal("10.00")
        assert reloaded.secret == [1, "two", 3]
        assert isinstance(reloaded.slug, Stringable) and str(reloaded.slug) == "hello"

        # the encrypted column holds ciphertext at rest, not the plaintext JSON
        raw_row = await db.fetch_one(
            sa.select(RichItem.__table__.c.secret).where(RichItem.__table__.c.id == created.id)
        )
        assert raw_row is not None
        assert '"two"' not in raw_row["secret"]
    finally:
        await db.execute(sa.schema.DropTable(RichItem.__table__))
        await db.dispose()
        set_application(None)


async def test_full_event_lifecycle_on_postgres(postgres_url: str) -> None:
    app = Application()
    app.instance("events", Dispatcher())
    set_application(app)
    db = ConnectionResolver({"default": {"url": postgres_url}})
    Gadget.set_connection(db)
    calls: list[str] = []

    class Recorder:
        async def _log(self, hook: str) -> None:
            calls.append(hook)

        async def creating(self, m: Any) -> None:
            await self._log("creating")

        async def created(self, m: Any) -> None:
            await self._log("created")

        async def updating(self, m: Any) -> None:
            await self._log("updating")

        async def updated(self, m: Any) -> None:
            await self._log("updated")

        async def retrieved(self, m: Any) -> None:
            await self._log("retrieved")

        async def deleted(self, m: Any) -> None:
            await self._log("deleted")

    try:
        await db.execute(sa.schema.CreateTable(Gadget.__table__))
        Gadget.observe(Recorder())

        widget = await Gadget.create(name="widget", qty=1)
        assert calls == ["creating", "created"]

        calls.clear()
        widget.qty = 2
        await widget.save()
        assert calls == ["updating", "updated"]

        calls.clear()
        await Gadget.find(widget.id)
        assert calls == ["retrieved"]

        calls.clear()
        await widget.delete()
        assert calls == ["deleted"]
    finally:
        await db.execute(sa.schema.DropTable(Gadget.__table__))
        await db.dispose()
        set_application(None)


# --- 09 DB-QUERY: A4 upsert / A5 sync / ModelCollection / QB breadth / cursor pagination ------


class Sku(Model):
    __table_name__ = "pg_skus"
    __fields__: ClassVar = {"sku": str, "price": int}
    __fillable__: ClassVar = ["sku", "price"]
    __timestamps__ = False


async def test_upsert_on_conflict_do_update_on_postgres(postgres_url: str) -> None:
    db = ConnectionResolver({"default": {"url": postgres_url}})
    Sku.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(Sku.__table__))
        await db.statement("CREATE UNIQUE INDEX ux_pg_skus_sku ON pg_skus (sku)")

        await Sku.upsert([{"sku": "A", "price": 10}, {"sku": "B", "price": 20}], ["sku"], ["price"])
        assert await Sku.count() == 2

        await Sku.upsert([{"sku": "A", "price": 99}], ["sku"], ["price"])
        assert await Sku.count() == 2
        a = await Sku.where(sku="A").first()
        assert a.price == 99
    finally:
        await db.execute(sa.schema.DropTable(Sku.__table__))
        await db.dispose()


class PgTag(Model):
    __table_name__ = "pg_tags"
    __fields__: ClassVar = {"name": str}
    __fillable__: ClassVar = ["name"]
    __timestamps__ = False


class PgPost(Model):
    __table_name__ = "pg_posts"
    __fields__: ClassVar = {"title": str}
    __fillable__: ClassVar = ["title"]
    __timestamps__ = False

    def tags(self) -> Any:
        return self.belongs_to_many(
            PgTag, pivot="pg_post_tag", foreign_pivot_key="post_id", related_pivot_key="tag_id"
        ).with_pivot("note")


_pg_pivot = sa.Table(
    "pg_post_tag",
    sa.MetaData(),
    sa.Column("post_id", sa.Integer),
    sa.Column("tag_id", sa.Integer),
    sa.Column("note", sa.String),
)


async def test_sync_preserves_pivot_data_on_postgres(postgres_url: str) -> None:
    db = ConnectionResolver({"default": {"url": postgres_url}})
    for model in (PgPost, PgTag):
        model.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(PgPost.__table__))
        await db.execute(sa.schema.CreateTable(PgTag.__table__))
        await db.execute(sa.schema.CreateTable(_pg_pivot))

        post = await PgPost.create(title="hi")
        a = await PgTag.create(name="a")
        b = await PgTag.create(name="b")
        c = await PgTag.create(name="c")
        await post.tags().attach(a.id, note="keep-me")
        await post.tags().attach(b.id, note="going-away")

        result = await post.tags().sync([a.id, c.id])
        assert isinstance(result, SyncResult)
        assert result.attached == [c.id]
        assert result.detached == [b.id]

        rows = await post.tags().get()
        by_name = {t.name: t for t in rows}
        assert set(by_name) == {"a", "c"}
        assert by_name["a"].pivot["note"] == "keep-me"  # retained row's pivot data survives (A5)
    finally:
        await db.execute(sa.schema.DropTable(_pg_pivot))
        await db.execute(sa.schema.DropTable(PgPost.__table__))
        await db.execute(sa.schema.DropTable(PgTag.__table__))
        await db.dispose()


class PgEvent(Model):
    __table_name__ = "pg_events"
    __fields__: ClassVar = {"name": str, "happened_at": dt.datetime}
    __fillable__: ClassVar = ["name", "happened_at"]
    __timestamps__ = False


async def test_qb_breadth_join_having_where_date_on_postgres(postgres_url: str) -> None:
    db = ConnectionResolver({"default": {"url": postgres_url}})
    PgEvent.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(PgEvent.__table__))
        await PgEvent.create(name="launch", happened_at=dt.datetime(2026, 6, 1, 9, 0))
        await PgEvent.create(name="ship", happened_at=dt.datetime(2026, 7, 1, 9, 0))
        await PgEvent.create(name="launch", happened_at=dt.datetime(2026, 6, 15, 9, 0))

        # where_date on a real timestamp column
        june_first = await PgEvent.where_date("happened_at", "=", dt.date(2026, 6, 1)).get()
        assert [e.name for e in june_first] == ["launch"]

        # having over a grouped aggregate — a raw (non-hydrating) builder, per the documented
        # convention: grouped queries return computed rows, not whole models. Postgres (unlike
        # SQLite/MySQL) rejects a SELECT-list alias in HAVING (matches the own having()
        # behavior — it's a real SQL-standard restriction, not an arvel gap), so `having_raw`
        # repeats the aggregate expression here rather than `having("total", ">", 1)`.
        grouped = await (
            Builder(PgEvent.__table__, db)
            .group_by("name")
            .select_raw("name, count(*) AS total")
            .having_raw("count(*) > ?", [1])
            .get()
        )
        assert [dict(r) for r in grouped] == [{"name": "launch", "total": 2}]

        # a real join against a second table
        await db.execute(sa.schema.CreateTable(PgTag.__table__))
        try:
            await PgTag.create(name="launch")
            joined = await (
                Builder(PgEvent.__table__, db)
                .join("pg_tags", "pg_events.name", "=", "pg_tags.name")
                .select_raw("pg_events.happened_at, pg_tags.name AS tag_name")
                .get()
            )
            assert {r["tag_name"] for r in joined} == {"launch"}
            assert len(joined) == 2  # both "launch" events match the one "launch" tag
        finally:
            await db.execute(sa.schema.DropTable(PgTag.__table__))
    finally:
        await db.execute(sa.schema.DropTable(PgEvent.__table__))
        await db.dispose()


class PgItem(Model):
    __table_name__ = "pg_items"
    __fields__: ClassVar = {"value": int}
    __fillable__: ClassVar = ["value"]
    __timestamps__ = False


async def test_cursor_paginate_walks_25_rows_in_3_pages_on_postgres(postgres_url: str) -> None:
    db = ConnectionResolver({"default": {"url": postgres_url}})
    PgItem.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(PgItem.__table__))
        for i in range(25):
            await PgItem.create(value=i)

        seen: list[int] = []
        cursor: str | None = None
        pages = 0
        while True:
            page = await PgItem.query().order_by("id").cursor_paginate(per_page=10, cursor=cursor)
            assert isinstance(page, CursorPaginator)
            pages += 1
            seen.extend(m.id for m in page)
            if not page.has_more_pages():
                break
            cursor = page.next_cursor()

        assert pages == 3
        assert seen == list(range(1, 26))  # no dup/skip, stable ordering

        # tie handling: order by a constant-valued column, pk is the implicit tiebreaker
        tied_seen: list[int] = []
        cursor = None
        for _ in range(10):
            page = (
                await PgItem.query().order_by("value").cursor_paginate(per_page=10, cursor=cursor)
            )
            tied_seen.extend(m.id for m in page)
            if not page.has_more_pages():
                break
            cursor = page.next_cursor()
        assert sorted(tied_seen) == list(range(1, 26))
        assert len(tied_seen) == len(set(tied_seen))
    finally:
        await db.execute(sa.schema.DropTable(PgItem.__table__))
        await db.dispose()


async def test_all_and_relation_get_return_model_collection_on_postgres(
    postgres_url: str,
) -> None:
    db = ConnectionResolver({"default": {"url": postgres_url}})
    Sku.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(Sku.__table__))
        await Sku.create(sku="X", price=1)
        result = await Sku.all()
        assert isinstance(result, ModelCollection)
        assert isinstance(await Builder(Sku.__table__, db).where_null("sku").get(), list)
    finally:
        await db.execute(sa.schema.DropTable(Sku.__table__))
        await db.dispose()


# --- E12: D4 has_attached (factory pivot seeding) + D7 relation-proxy symmetry ------------------


class PgRole(Model):
    __table_name__ = "pg_e12_roles"
    __fields__: ClassVar = {"name": str}
    __fillable__: ClassVar = ["name"]
    __timestamps__ = False


class PgUser(Model):
    __table_name__ = "pg_e12_users"
    __fields__: ClassVar = {"name": str}
    __fillable__: ClassVar = ["name"]
    __timestamps__ = False

    def roles(self) -> Any:
        return self.belongs_to_many(
            PgRole,
            pivot="pg_e12_role_user",
            foreign_pivot_key="user_id",
            related_pivot_key="role_id",
        )


class PgRoleFactory(Factory[PgRole]):
    model = PgRole

    def definition(self) -> dict[str, Any]:
        return {"name": "editor"}


class PgUserFactory(Factory[PgUser]):
    model = PgUser

    def definition(self) -> dict[str, Any]:
        return {"name": "ada"}


_pg_role_user = sa.Table(
    "pg_e12_role_user",
    sa.MetaData(),
    sa.Column("user_id", sa.Integer),
    sa.Column("role_id", sa.Integer),
    sa.Column("level", sa.Integer),
)


async def _setup_pg_pivot(db: ConnectionResolver) -> None:
    for model in (PgUser, PgRole):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    await db.execute(sa.schema.CreateTable(_pg_role_user))


async def _teardown_pg_pivot(db: ConnectionResolver) -> None:
    await db.execute(sa.schema.DropTable(_pg_role_user))
    await db.execute(sa.schema.DropTable(PgUser.__table__))
    await db.execute(sa.schema.DropTable(PgRole.__table__))


async def test_has_attached_seeds_related_and_pivot_rows_on_postgres(postgres_url: str) -> None:
    """D4: `has_attached` creates the related rows AND the pivot rows, writing pivot_data."""
    db = ConnectionResolver({"default": {"url": postgres_url}})
    await _setup_pg_pivot(db)
    try:
        user = await (
            PgUserFactory().has_attached(PgRoleFactory(), "roles", {"level": 2}, count=3).create()
        )

        roles = await PgRole.all()
        assert len(roles) == 3  # (a) the related rows exist

        pivot_rows = [
            dict(r)
            for r in await db.fetch_all(
                sa.select(_pg_role_user).where(_pg_role_user.c.user_id == user.id)
            )
        ]
        assert len(pivot_rows) == 3  # (b) a pivot row per created role
        assert all(row["level"] == 2 for row in pivot_rows)  # (c) pivot column read from the DB
        assert {row["role_id"] for row in pivot_rows} == {r.id for r in roles}
    finally:
        await _teardown_pg_pivot(db)
        await db.dispose()


async def test_belongs_to_many_proxy_full_builder_scoped_on_postgres(postgres_url: str) -> None:
    """D7: a BelongsToMany proxy answers where_in/pluck/where_pivot+where/count/first, scoped to
    the parent's attached rows — asserted against a hand-computed expectation from the same DB."""
    db = ConnectionResolver({"default": {"url": postgres_url}})
    await _setup_pg_pivot(db)
    try:
        user = await PgUser.create(name="ada")
        other = await PgUser.create(name="bob")
        a = await PgRole.create(name="admin")
        b = await PgRole.create(name="editor")
        c = await PgRole.create(name="viewer")
        outside = await PgRole.create(name="outsider")
        await user.roles().attach(a.id)
        await user.roles().attach(b.id)
        await user.roles().attach(c.id)
        await other.roles().attach(outside.id)  # a different parent's attachment

        # where_in ∩ attached, scoped to `user` — `outside` is a valid role id but attached to
        # `other`, never `user`, so it's absent even though it's in the id filter.
        got = await user.roles().where_in("id", [a.id, c.id, outside.id]).pluck("name")
        assert sorted(got) == ["admin", "viewer"]

        # where_pivot composes with the proxied builder
        await user.roles().detach()
        await user.roles().attach(a.id)
        await user.roles().attach(b.id, level=2)
        active = await user.roles().where_pivot("level", 2).where("name", "=", "editor").count()
        assert active == 1

        # first() (previously silently broken — base Relation.first() filtered the related table
        # by a pivot column it doesn't have)
        first = await user.roles().order_by("name").first()
        assert first is not None and first.name == "admin"

        # an unattached parent yields [], not the whole related table
        lonely = await PgUser.create(name="lonely")
        assert await lonely.roles().where_in("id", [a.id]).get() == []
    finally:
        await _teardown_pg_pivot(db)
        await db.dispose()


async def test_belongs_to_many_proxy_chunk_and_each_stay_scoped_across_pages_on_postgres(
    postgres_url: str,
) -> None:
    """Regression (QA, real Postgres): chunk_by_id/chunk/each over a pivot proxy must stay
    parent-scoped on EVERY page, not just the first. Root cause: chunk_by_id/chunk snapshot
    _wheres/_limit/_offset before their first get() — the pivot WHERE IN only lands in _wheres
    *during* that first get() (via _ensure_prepared), so an early snapshot predates it, and the
    once-guard then blocks it from ever being re-applied on later pages. Repro that leaked:
    attached {1,3,5}, unattached {2,4,6} -> chunk_by_id(2) yielded [[1,3],[4,5],[6]]."""
    db = ConnectionResolver({"default": {"url": postgres_url}})
    await _setup_pg_pivot(db)
    try:
        user = await PgUser.create(name="ada")
        roles = [await PgRole.create(name=f"role{i}") for i in range(1, 7)]  # ids 1..6, in order
        attached = [roles[0], roles[2], roles[4]]  # roles 1, 3, 5
        attached_ids = {r.id for r in attached}
        for role in attached:
            await user.roles().attach(role.id)
        # roles 2, 4, 6 stay unattached — exactly the ids the leak surfaced

        seen_by_id: list[Any] = []
        await user.roles().order_by("id").chunk_by_id(2, lambda rows: seen_by_id.extend(rows))
        assert {r.id for r in seen_by_id} == attached_ids
        assert len(seen_by_id) == 3  # no dup, no leak, spans 2 pages (size=2, 3 rows)

        seen_chunk: list[Any] = []
        await user.roles().order_by("id").chunk(2, lambda rows: seen_chunk.extend(rows))
        assert {r.id for r in seen_chunk} == attached_ids
        assert len(seen_chunk) == 3

        seen_each: list[Any] = []
        await user.roles().order_by("id").each(lambda r: seen_each.append(r), chunk_size=2)
        assert {r.id for r in seen_each} == attached_ids
        assert len(seen_each) == 3

        # an unattached parent chunked yields nothing, on every path
        lonely = await PgUser.create(name="lonely")
        empty: list[Any] = []
        await lonely.roles().chunk_by_id(2, lambda rows: empty.extend(rows))
        await lonely.roles().chunk(2, lambda rows: empty.extend(rows))
        await lonely.roles().each(lambda r: empty.append(r))
        assert empty == []
    finally:
        await _teardown_pg_pivot(db)
        await db.dispose()


async def test_belongs_to_many_proxy_aggregates_stay_scoped_on_postgres(postgres_url: str) -> None:
    """Regression (review, real Postgres): sum/avg/min/max over a deferred-pivot proxy must be
    parent-scoped, not the whole related table. Root cause: the shared ``_aggregate()`` (backing
    all four) never called ``_ensure_prepared()``, unlike its sibling ``count()`` — so
    ``.sum("id")`` etc. ran against every related row. Repro: user attached to roles {1,2} of 4 ->
    sum("id") was 10 (1+2+3+4) instead of 3; max("id") was 4, a different parent's row."""
    db = ConnectionResolver({"default": {"url": postgres_url}})
    await _setup_pg_pivot(db)
    try:
        user = await PgUser.create(name="ada")
        roles = [await PgRole.create(name=f"role{i}") for i in range(1, 5)]  # ids 1..4
        await user.roles().attach(roles[0].id)
        await user.roles().attach(roles[1].id)
        # roles 3, 4 stay unattached — a leaking aggregate would pull them into sum/avg/max/min

        assert await user.roles().sum("id") == roles[0].id + roles[1].id
        assert await user.roles().avg("id") == pytest.approx((roles[0].id + roles[1].id) / 2)
        assert await user.roles().max("id") == roles[1].id
        assert await user.roles().min("id") == roles[0].id

        lonely = await PgUser.create(name="lonely")
        assert await lonely.roles().sum("id") is None  # SQL SUM/MIN/MAX over 0 rows -> NULL
    finally:
        await _teardown_pg_pivot(db)
        await db.dispose()


class PgTagM(Model):
    __table_name__ = "pg_e12_tags"
    __fields__: ClassVar = {"name": str}
    __fillable__: ClassVar = ["name"]
    __timestamps__ = False

    def posts(self) -> Any:
        return self.morphed_by_many(PgPostM, "pg_e12_taggable")


class PgPostM(Model):
    __table_name__ = "pg_e12_posts"
    __fields__: ClassVar = {"title": str}
    __fillable__: ClassVar = ["title"]
    __timestamps__ = False

    def tags(self) -> Any:
        return self.morph_to_many(PgTagM, "pg_e12_taggable")


class PgTagMFactory(Factory[PgTagM]):
    model = PgTagM

    def definition(self) -> dict[str, Any]:
        return {"name": "python"}


class PgPostMFactory(Factory[PgPostM]):
    model = PgPostM

    def definition(self) -> dict[str, Any]:
        return {"title": "hello"}


_pg_e12_taggable = sa.Table(
    "pg_e12_taggables",
    sa.MetaData(),
    sa.Column("pg_e12_taggable_id", sa.Integer),
    sa.Column("pg_e12_taggable_type", sa.String),
    sa.Column("pg_tag_m_id", sa.Integer),
)


async def test_morph_to_many_has_attached_and_proxy_scoped_on_postgres(postgres_url: str) -> None:
    """D4 (morph_to_many) + D7 (MorphToMany/MorphedByMany proxy symmetry)."""
    db = ConnectionResolver({"default": {"url": postgres_url}})
    for model in (PgPostM, PgTagM):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    await db.execute(sa.schema.CreateTable(_pg_e12_taggable))
    try:
        # D4: has_attached on a morph_to_many relation
        post = await PgPostMFactory().has_attached(PgTagMFactory(), "tags").create()
        tags = await post.tags().get()
        assert len(tags) == 1
        pivot_rows = [
            dict(r)
            for r in await db.fetch_all(
                sa.select(_pg_e12_taggable).where(_pg_e12_taggable.c.pg_e12_taggable_id == post.id)
            )
        ]
        assert len(pivot_rows) == 1
        assert pivot_rows[0]["pg_e12_taggable_type"]  # the polymorphic discriminator was written
        assert pivot_rows[0]["pg_tag_m_id"] == tags[0].id

        # D7: MorphToMany + MorphedByMany proxy the full builder, scoped by id AND morph type
        other_post = await PgPostM.create(title="other")
        rust = await PgTagM.create(name="rust")
        await other_post.tags().attach(rust.id)

        names = await post.tags().where_in("id", [tags[0].id, rust.id]).pluck("name")
        assert names == [tags[0].name]  # rust belongs to `other_post`, excluded by the pivot scope

        by_tag = await tags[0].posts().where_in("id", [post.id, other_post.id]).pluck("title")
        assert by_tag == [post.title]  # other_post never attached to this tag
    finally:
        await db.execute(sa.schema.DropTable(_pg_e12_taggable))
        await db.execute(sa.schema.DropTable(PgPostM.__table__))
        await db.execute(sa.schema.DropTable(PgTagM.__table__))
        await db.dispose()


async def test_morph_to_many_proxy_aggregates_stay_scoped_on_postgres(postgres_url: str) -> None:
    """Same aggregate-scope regression as the belongs-to-many case, over a morph_to_many proxy —
    the shared ``_aggregate()`` fix covers every pivot shape at the one root."""
    db = ConnectionResolver({"default": {"url": postgres_url}})
    for model in (PgPostM, PgTagM):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    await db.execute(sa.schema.CreateTable(_pg_e12_taggable))
    try:
        post = await PgPostM.create(title="hello")
        tags = [await PgTagM.create(name=f"tag{i}") for i in range(1, 5)]  # ids 1..4
        await post.tags().attach(tags[0].id)
        await post.tags().attach(tags[1].id)
        # tags 3, 4 stay unattached

        assert await post.tags().sum("id") == tags[0].id + tags[1].id
        assert await post.tags().max("id") == tags[1].id
        assert await post.tags().min("id") == tags[0].id
    finally:
        await db.execute(sa.schema.DropTable(_pg_e12_taggable))
        await db.execute(sa.schema.DropTable(PgPostM.__table__))
        await db.execute(sa.schema.DropTable(PgTagM.__table__))
        await db.dispose()
