"""arvel.activitylog — Spatie-style activity log / audit trail: the fluent activity() logger and
the LogsActivity mixin (auto-logs create/update/delete with {old, attributes})."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.activitylog import Activity, LogsActivity, activity
from arvel.database import ConnectionResolver, Model


class Post(LogsActivity, Model):  # mixin BEFORE Model so the lifecycle hooks run (MRO)
    __fields__ = {"title": str, "views": int}
    __fillable__ = ["title", "views"]


class Author(Model):
    __fields__ = {"name": str}
    __fillable__ = ["name"]


class Article(LogsActivity, Model):
    """Only logs `created` — never `updated`/`deleted` — to exercise the skip branch."""

    __fields__ = {"title": str}
    __fillable__ = ["title"]
    __logs_events__ = ("created",)


class Note(LogsActivity, Model):
    """Restricted to a subset of columns via `__log_attributes__`."""

    __fields__ = {"title": str, "secret": str}
    __fillable__ = ["title", "secret"]
    __log_attributes__ = ["title"]


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    for model in (Activity, Post, Author, Article, Note):
        model.set_connection(db)
        await db.execute(sa.schema.CreateTable(model.__table__))
    return db


async def test_activity_logger_freeform() -> None:
    db = await _setup()
    try:
        logged = await activity().log("system booted")
        assert logged.log_name == "default"
        assert logged.description == "system booted"
        assert len(await Activity.get()) == 1
    finally:
        await db.dispose()


async def test_activity_logger_subject_causer_properties() -> None:
    db = await _setup()
    try:
        post = await Post.create(title="hi", views=0)
        logged = await (
            activity("audit").performed_on(post).with_properties({"ip": "1.2.3.4"}).log("viewed")
        )
        assert logged.log_name == "audit"
        from arvel.database import morph_type_of

        assert logged.subject_type == morph_type_of(Post)
        assert logged.subject_id == post.id
        assert logged.properties == {"ip": "1.2.3.4"}
    finally:
        await db.dispose()


async def test_logs_activity_on_create_update_delete() -> None:
    db = await _setup()
    try:
        post = await Post.create(title="hi", views=1)
        created = await Activity.where(event="created").first()
        assert created is not None
        assert created.subject_id == post.id
        assert created.properties["attributes"]["title"] == "hi"

        post.title = "bye"
        await post.save()
        updated = await Activity.where(event="updated").first()
        assert updated is not None
        assert updated.properties["old"]["title"] == "hi"
        assert updated.properties["attributes"]["title"] == "bye"

        await post.delete()
        deleted = await Activity.where(event="deleted").first()
        assert deleted is not None
        assert deleted.properties["old"]["title"] == "bye"
    finally:
        await db.dispose()


async def test_log_only_dirty_skips_empty_update() -> None:
    db = await _setup()
    try:
        post = await Post.create(title="hi", views=1)
        await post.save()  # nothing changed → no "updated" activity
        assert len(await Activity.where(event="updated").get()) == 0
    finally:
        await db.dispose()


def test_activity_changes_extracts_old_and_attributes() -> None:
    entry = Activity(properties={"old": {"a": 1}, "attributes": {"a": 2}, "extra": "ignored"})
    assert entry.changes() == {"old": {"a": 1}, "attributes": {"a": 2}}


def test_activity_changes_is_empty_for_non_dict_properties() -> None:
    entry = Activity(properties=None)
    assert entry.changes() == {}


async def test_use_log_switches_the_log_name() -> None:
    db = await _setup()
    try:
        logged = await activity("default").use_log("audit").log("switched")
        assert logged.log_name == "audit"
    finally:
        await db.dispose()


async def test_caused_by_and_with_property_are_honored() -> None:
    db = await _setup()
    try:
        author = await Author.create(name="ada")
        logged = await activity().caused_by(author).with_property("k", "v").log("did a thing")
        from arvel.database import morph_type_of

        assert logged.causer_type == morph_type_of(Author)
        assert logged.causer_id == author.id
        assert logged.properties == {"k": "v"}
    finally:
        await db.dispose()


async def test_logs_activity_skips_events_not_in_the_allow_list() -> None:
    db = await _setup()
    try:
        article = await Article.create(title="v1")
        assert len(await Activity.where(event="created").get()) == 1

        article.title = "v2"
        await article.save()  # "updated" not in __logs_events__: no activity recorded
        assert len(await Activity.where(event="updated").get()) == 0
    finally:
        await db.dispose()


async def test_log_attributes_restricts_the_recorded_columns() -> None:
    db = await _setup()
    try:
        note = await Note.create(title="public", secret="shh")
        created = await Activity.where(event="created").first()
        assert created is not None
        assert created.properties["attributes"] == {"title": "public"}  # "secret" excluded
        assert note.secret == "shh"
    finally:
        await db.dispose()
