"""arvel.activitylog — Spatie-style activity log / audit trail: the fluent activity() logger and
the LogsActivity mixin (auto-logs create/update/delete with {old, attributes})."""

from __future__ import annotations

import sqlalchemy as sa

from arvel.activitylog import Activity, LogsActivity, activity
from arvel.database import ConnectionResolver, Model


class Post(LogsActivity, Model):  # mixin BEFORE Model so the lifecycle hooks run (MRO)
    __fields__ = {"title": str, "views": int}
    __fillable__ = ["title", "views"]


async def _setup() -> ConnectionResolver:
    db = ConnectionResolver()
    Activity.set_connection(db)
    Post.set_connection(db)
    await db.execute(sa.schema.CreateTable(Activity.__table__))
    await db.execute(sa.schema.CreateTable(Post.__table__))
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
        assert logged.subject_type == "Post"
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
