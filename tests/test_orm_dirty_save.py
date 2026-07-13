"""Dirty-only saves + the instance CRUD surface: update()/push()/first_or_new/
sole()/find_many(). A save must write only changed columns so concurrent
writers can't clobber each other's untouched fields."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model


class NoteD(Model):
    __fields__ = {"title": str, "body": str, "views": int}
    __fillable__ = ["title", "body", "views"]
    __timestamps__ = False


class StampD(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (NoteD, StampD):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    return db


async def test_concurrent_updates_to_different_columns_both_survive() -> None:
    db = await _setup()
    try:
        note = await NoteD.create(title="t", body="b", views=0)
        first = await NoteD.find(note.id)
        second = await NoteD.find(note.id)
        first.title = "t2"
        await first.save()
        second.views = 9  # stale title in memory, but it only writes what IT changed
        await second.save()
        fresh = await NoteD.find(note.id)
        assert fresh.title == "t2"  # not clobbered back to "t"
        assert fresh.views == 9
    finally:
        await db.dispose()


async def test_clean_save_issues_no_update_and_keeps_updated_at() -> None:
    db = await _setup()
    try:
        row = await StampD.create(name="s")
        loaded = await StampD.find(row.id)
        before = loaded.updated_at
        db.enable_query_log()
        assert await loaded.save() is True
        assert db.get_query_log() == []  # clean model → no SQL at all
        assert loaded.updated_at == before
    finally:
        db.disable_query_log()
        await db.dispose()


async def test_primary_key_change_updates_by_original_key() -> None:
    db = await _setup()
    try:
        note = await NoteD.create(title="a", body="x", views=0)
        loaded = await NoteD.find(note.id)
        old_id = loaded.id
        loaded.id = old_id + 100
        await loaded.save()
        assert await NoteD.find(old_id) is None
        moved = await NoteD.find(old_id + 100)
        assert moved is not None and moved.title == "a"
    finally:
        await db.dispose()


async def test_instance_update_fills_and_saves() -> None:
    db = await _setup()
    try:
        note = await NoteD.create(title="a", body="x", views=0)
        assert await note.update({"title": "b"}) is True
        fresh = await NoteD.find(note.id)
        assert fresh.title == "b" and fresh.body == "x"
    finally:
        await db.dispose()


async def test_push_saves_model_and_loaded_relations() -> None:
    db = await _setup()

    class ItemD(Model):
        __fields__ = {"label": str, "boxd_id": int}
        __fillable__ = ["label", "boxd_id"]
        __timestamps__ = False

    class BoxD(Model):
        __fields__ = {"name": str}
        __fillable__ = ["name"]
        __timestamps__ = False

        def items(self) -> object:
            return self.has_many(ItemD, foreign_key="boxd_id")

    try:
        for model in (ItemD, BoxD):
            model.set_connection(db)
            await db.execute(sa.schema.CreateTable(model.__table__))
        box = await BoxD.create(name="b")
        await box.items().create(label="i1")
        [loaded] = await BoxD.with_("items").get()
        loaded.name = "b2"
        loaded.relation("items")[0].label = "i1x"
        await loaded.push()
        assert (await BoxD.find(box.id)).name == "b2"
        assert (await ItemD.query().first()).label == "i1x"
    finally:
        await db.dispose()


async def test_first_or_new_returns_unsaved_instance() -> None:
    db = await _setup()
    try:
        note = await NoteD.first_or_new({"title": "ghost"}, {"body": "b", "views": 0})
        assert note.title == "ghost" and not note._exists
        assert await NoteD.query().count() == 0  # nothing persisted
        existing = await NoteD.create(title="real", body="x", views=1)
        again = await NoteD.first_or_new({"title": "real"})
        assert again.id == existing.id and again._exists
    finally:
        await db.dispose()


async def test_sole_raises_on_none_and_on_many() -> None:
    from arvel.database.builder import MultipleRecordsFound
    from arvel.database.model import ModelNotFound

    db = await _setup()
    try:
        with pytest.raises(ModelNotFound):
            await NoteD.query().sole()
        await NoteD.create(title="one", body="x", views=0)
        got = await NoteD.query().sole()
        assert got.title == "one"
        await NoteD.create(title="two", body="x", views=0)
        with pytest.raises(MultipleRecordsFound):
            await NoteD.query().sole()
    finally:
        await db.dispose()


async def test_find_many_returns_matching_models() -> None:
    db = await _setup()
    try:
        a = await NoteD.create(title="a", body="x", views=0)
        await NoteD.create(title="b", body="x", views=0)
        c = await NoteD.create(title="c", body="x", views=0)
        found = await NoteD.find_many([a.id, c.id, 999])
        assert sorted(n.title for n in found) == ["a", "c"]
    finally:
        await db.dispose()
