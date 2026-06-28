"""Coverage — Model edge paths: finders, change-tracking, casts via container (doc 07)."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model
from arvel.database.model import ModelNotFound


class Note(Model):
    __fields__ = {"title": str, "views": int}
    __fillable__ = ["title", "views"]


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    Note.set_connection(db)
    await db.execute(sa.schema.CreateTable(Note.__table__))
    return db


async def test_find_or_fail_misses() -> None:
    db = await _setup()
    try:
        with pytest.raises(ModelNotFound):
            await Note.find_or_fail(999)
    finally:
        await db.dispose()


async def test_increment_decrement_and_change_tracking() -> None:
    db = await _setup()
    try:
        note = await Note.create(title="t", views=1)
        await note.increment("views", 4)
        await note.decrement("views", 2)
        assert note.views == 3
        note.title = "changed"
        assert note.was_changed("title")
        assert note.get_original("title") == "t"
        assert "title" in note.get_original()
    finally:
        await db.dispose()


async def test_refresh_and_first_or_create_existing() -> None:
    db = await _setup()
    try:
        note = await Note.create(title="orig", views=0)
        again = await Note.first_or_create({"title": "orig"}, {"views": 5})
        assert again.id == note.id  # found existing, not created
        await Note.where(id=note.id).update({"title": "db-changed"})
        await note.refresh()
        assert note.title == "db-changed"
    finally:
        await db.dispose()


async def test_make_hidden_visible() -> None:
    db = await _setup()
    try:
        note = await Note.create(title="t", views=9)
        note.make_hidden("views")
        assert "views" not in note.to_dict()
        note.make_visible("views")
        assert "views" in note.to_dict()
    finally:
        await db.dispose()


async def test_encrypted_and_hashed_casts_via_container() -> None:
    from arvel.kernel import Application, set_application
    from arvel.security import Encrypter, Hasher

    app = Application()
    app.instance("encrypter", Encrypter(Encrypter.generate_key()))
    app.instance("hash", Hasher())
    set_application(app)

    class Secret(Model):
        __fields__ = {"ssn": str, "pw": str}
        __fillable__ = ["ssn", "pw"]
        __casts__ = {"ssn": "encrypted", "pw": "hashed"}

    db = ConnectionResolver()
    Secret.set_connection(db)
    try:
        await db.execute(sa.schema.CreateTable(Secret.__table__))
        secret = await Secret.create(ssn="123-45-6789", pw="s3cret")
        assert secret._attributes["ssn"] != "123-45-6789"  # stored encrypted
        assert secret._attributes["pw"].startswith("$argon2")  # stored hashed
        assert secret.ssn == "123-45-6789"  # decrypted on read
    finally:
        set_application(None)
        await db.dispose()
