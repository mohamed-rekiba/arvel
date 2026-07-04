"""Seeder (doc 10): `call_once` skips a seeder class already run this process; `WithoutModelEvents`
suppresses model lifecycle events for its duration (Laravel `WithoutModelEvents` trait)."""

from __future__ import annotations

from typing import ClassVar

import sqlalchemy as sa

from arvel.database import ConnectionResolver, Model, Seeder, WithoutModelEvents
from arvel.database.model_events import EVENTS_SUPPRESSED
from arvel.events import Dispatcher
from arvel.kernel import Application, set_application

RUN_COUNT: list[str] = []


class RolesSeeder(Seeder):
    async def run(self) -> None:
        RUN_COUNT.append("roles")


class UsersSeeder(Seeder):
    async def run(self) -> None:
        await self.call_once(RolesSeeder)


class PostsSeeder(Seeder):
    async def run(self) -> None:
        await self.call_once(RolesSeeder)


async def test_call_once_runs_a_seeder_class_only_once_per_process() -> None:
    RUN_COUNT.clear()
    root = Seeder()
    await root.call_once(RolesSeeder, RolesSeeder)  # duplicate in the same call too
    await UsersSeeder().run()
    await PostsSeeder().run()
    assert RUN_COUNT == ["roles"]


class Widget(Model):
    __fields__: ClassVar = {"name": str}
    __fillable__: ClassVar = ["name"]


async def test_without_model_events_suppresses_creating_and_saved() -> None:
    db = ConnectionResolver()
    Widget.set_connection(db)
    await db.execute(sa.schema.CreateTable(Widget.__table__))
    app = Application()
    calls: list[str] = []
    dispatcher = Dispatcher()
    dispatcher.listen("Widget.creating", lambda w: calls.append("creating"))
    dispatcher.listen("Widget.saved", lambda w: calls.append("saved"))
    app.instance("events", dispatcher)
    set_application(app)
    try:
        with WithoutModelEvents():
            await Widget.create(name="silent")
        assert calls == []  # suppressed inside the block

        await Widget.create(name="loud")
        assert calls == ["creating", "saved"]  # normal dispatch resumes after the block
    finally:
        set_application(None)
        await db.dispose()


def test_without_model_events_resets_even_on_exception() -> None:
    assert EVENTS_SUPPRESSED.get() is False
    try:
        with WithoutModelEvents():
            assert EVENTS_SUPPRESSED.get() is True
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert EVENTS_SUPPRESSED.get() is False


async def test_call_once_dedup_is_per_run_not_process_lifetime() -> None:
    # regression: without a per-run reset, a repeated db:seed / long-lived worker would
    # silently skip every once-seeder after the first run.
    from arvel.database.seeder import _called_once, reset_called_once

    reset_called_once()  # isolate from any prior test's call_once state
    RUN_COUNT.clear()
    await UsersSeeder().run()
    assert RUN_COUNT == ["roles"]
    await UsersSeeder().run()  # same process, no reset -> skipped
    assert RUN_COUNT == ["roles"]
    reset_called_once()
    assert _called_once == set()
    await UsersSeeder().run()  # fresh run -> runs again
    assert RUN_COUNT == ["roles", "roles"]
