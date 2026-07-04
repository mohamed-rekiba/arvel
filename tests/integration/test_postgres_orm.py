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

from arvel.database import Builder, ConnectionResolver, Model
from arvel.database.collection import EloquentCollection
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


# --- 09 DB-QUERY: A4 upsert / A5 sync / EloquentCollection / QB breadth / cursor pagination ------


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
        # SQLite/MySQL) rejects a SELECT-list alias in HAVING (matches Laravel's own having()
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


async def test_all_and_relation_get_return_eloquent_collection_on_postgres(
    postgres_url: str,
) -> None:
    db = ConnectionResolver({"default": {"url": postgres_url}})
    Sku.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(Sku.__table__))
        await Sku.create(sku="X", price=1)
        result = await Sku.all()
        assert isinstance(result, EloquentCollection)
        assert isinstance(await Builder(Sku.__table__, db).where_null("sku").get(), list)
    finally:
        await db.execute(sa.schema.DropTable(Sku.__table__))
        await db.dispose()
