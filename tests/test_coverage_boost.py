"""Targeted coverage for thin/edge paths: the Seeder base, the CLI Spinner, Job.dispatch_after
(classmethod rail), and DatabaseNotification.mark_as_read/unread idempotency."""

from __future__ import annotations

import io
import time
from typing import Any

import pytest
import sqlalchemy as sa

from arvel.console.spinner import Spinner
from arvel.database import ConnectionResolver, Factory, Seeder


class _TTY(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_spinner_animates_on_a_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    out = _TTY()
    with Spinner("working", stream=out):
        time.sleep(0.12)  # let the daemon thread emit at least one frame
    text = out.getvalue()
    assert "working" in text  # a frame was written
    assert "\r\033[2K" in text  # the line was cleared on exit


def test_spinner_is_noop_without_a_tty() -> None:
    out = io.StringIO()  # isatty() is False
    with Spinner("x", stream=out):
        time.sleep(0.02)
    assert out.getvalue() == ""  # no escape codes for piped output


def test_factory_faker_is_lazy_and_memoized() -> None:
    factory: Any = Factory()
    first = factory.faker
    assert first is factory.faker  # memoized on the instance


def test_factory_definition_is_abstract() -> None:
    with pytest.raises(NotImplementedError):
        Factory().definition()


async def test_seeder_base_run_is_abstract() -> None:
    with pytest.raises(NotImplementedError):
        await Seeder().run()


async def test_seeder_call_chains_children() -> None:
    ran: list[str] = []

    class Child(Seeder):
        async def run(self) -> None:
            ran.append("child")

    class Root(Seeder):
        async def run(self) -> None:
            await self.call(Child)

    await Root().run()
    assert ran == ["child"]


async def test_job_dispatch_after_classmethod_persists() -> None:
    from taskiq import InMemoryBroker

    from arvel.kernel import Application, set_application
    from arvel.queue import Job, QueuedJob, QueueManager

    app = Application()
    db = ConnectionResolver()
    app.instance("db", db)
    app.instance("queue", QueueManager(app, broker=InMemoryBroker()))
    set_application(app)
    QueuedJob.set_connection(db)
    await db.execute(sa.schema.CreateTable(QueuedJob.__table__))

    class _Later(Job):
        async def handle(self) -> Any:
            return None

    try:
        await _Later.dispatch_after(60)  # the Job.dispatch_after classmethod rail
        assert len(await QueuedJob.all()) == 1
    finally:
        set_application(None)
        await db.dispose()


async def test_database_notification_mark_read_unread_idempotent() -> None:
    from arvel.notifications import DatabaseNotification

    db = ConnectionResolver()
    DatabaseNotification.set_connection(db)
    await db.execute(sa.schema.CreateTable(DatabaseNotification.__table__))
    try:
        note = await DatabaseNotification.create(
            type="T", notifiable_type="U", notifiable_id="1", data={}, read_at=None
        )
        assert note.unread
        await note.mark_as_read()
        assert note.read
        await note.mark_as_read()  # idempotent — already read, no re-save
        await note.mark_as_unread()
        assert note.unread  # back to unread
        await note.mark_as_unread()  # idempotent — already unread
    finally:
        await db.dispose()
