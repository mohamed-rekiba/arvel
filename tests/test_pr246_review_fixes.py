"""Regression pins for the PR-246 review findings."""

from __future__ import annotations

from typing import Any

import pytest


# --- console: bool is not an exit code ----------------------------------------
async def test_true_return_is_not_an_exit_code() -> None:
    from arvel.console import Command
    from arvel.console.kernel import run_command_class
    from arvel.kernel.application import Application
    from arvel.kernel.globals import set_application

    class Flagged(Command):
        signature = "demo:flag"
        description = "returns True like a success flag"

        async def handle(self) -> bool:
            return True

    set_application(Application())
    try:
        run_command_class(Flagged)  # must NOT raise typer.Exit(code=True)
    finally:
        set_application(None)


# --- cache + auth: best-effort dispatch survives a broken listener -------------
async def test_cache_event_listener_failure_does_not_fail_the_operation() -> None:
    from arvel.cache import CacheHit, CacheManager
    from arvel.events.dispatcher import Dispatcher
    from arvel.kernel.application import Application
    from arvel.kernel.globals import set_application

    app = Application()
    dispatcher = Dispatcher()

    def explode(event: Any) -> None:
        raise RuntimeError("listener bug")

    dispatcher.listen(CacheHit, explode)
    app.instance("events", dispatcher)
    set_application(app)
    try:
        cache = CacheManager(app).driver("array")
        await cache.put("k", "v")
        assert await cache.get("k") == "v"  # the hit event's broken listener is contained
    finally:
        set_application(None)


# --- mail: round-robin without mailers is a clear config error -----------------
async def test_round_robin_empty_raises_config_error() -> None:
    from email.message import EmailMessage

    from arvel.mail import RoundRobinTransport

    with pytest.raises(RuntimeError, match="no mailers configured"):
        await RoundRobinTransport([]).send(EmailMessage())


# --- db: statement() writes hit the query log ----------------------------------
async def test_statement_records_in_query_log() -> None:
    from arvel.database import ConnectionResolver

    db = ConnectionResolver()
    try:
        await db.statement("CREATE TABLE t (id INTEGER)")
        db.enable_query_log()
        await db.statement("INSERT INTO t (id) VALUES (1)")
        log = db.get_query_log()
        assert len(log) == 1 and "INSERT INTO t" in log[0]["sql"]
    finally:
        db.disable_query_log()
        await db.dispose()


# --- testing fakes: count=0 means "none" ---------------------------------------
def test_assert_sent_count_zero_passes_when_nothing_sent() -> None:
    from arvel.testing import FakeMailer

    class Welcome:
        pass

    FakeMailer().assert_sent(Welcome, count=0)  # must pass


async def test_assert_pushed_count_zero_and_after_commit_recorded() -> None:
    from arvel.testing import FakeQueue

    class JobA:
        pass

    fake = FakeQueue()
    fake.assert_pushed(JobA, count=0)  # must pass
    await fake.push(JobA, (1,), {}, queue="mail", after_commit=True)
    assert fake.pushed[0][4] is True  # after_commit recorded, not dropped
    fake.assert_pushed(JobA, count=1, queue="mail")


# --- search: soft-delete flag auto-declared filterable -------------------------
def test_effective_filterable_includes_soft_delete_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import arvel.search as search

    class Doc:
        @classmethod
        def searchable_filterable(cls) -> list[str]:
            return ["status"]

    class On:
        soft_delete = True

    class Off:
        soft_delete = False

    monkeypatch.setattr(search, "SearchSettings", lambda: On())
    assert search.effective_filterable(Doc) == ["status", "__soft_deleted"]
    monkeypatch.setattr(search, "SearchSettings", lambda: Off())
    assert search.effective_filterable(Doc) == ["status"]
