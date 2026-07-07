"""Broadcasting (5.7) — a `ShouldBroadcast` event is queued by default; `ShouldBroadcastNow` stays
inline; a queued broadcast composes with after-commit (dropped on rollback)."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.broadcasting import LogBroadcaster
from arvel.broadcasting.provider import BroadcastServiceProvider
from arvel.database.connections import ConnectionResolver
from arvel.events import Dispatcher, ShouldBroadcast, ShouldBroadcastNow
from arvel.kernel.application import Application
from arvel.kernel.globals import set_application
from arvel.queue.provider import QueueServiceProvider


class Pinged(ShouldBroadcast):
    def broadcast_on(self) -> list[str]:
        return ["room"]

    def broadcast_as(self) -> str:
        return "pinged"


class PingedNow(ShouldBroadcastNow):
    def broadcast_on(self) -> list[str]:
        return ["room"]

    def broadcast_as(self) -> str:
        return "pinged-now"


class Boom(Exception):
    pass


@pytest.fixture
async def ctx() -> Any:
    app = Application()
    events = Dispatcher(app)
    app.instance("events", events)
    BroadcastServiceProvider(app).register()
    QueueServiceProvider(app).register()
    set_application(app)
    manager = app.make("queue")
    db = ConnectionResolver({"default": {"url": "sqlite+aiosqlite://"}})
    try:
        yield app, events, manager, db
    finally:
        set_application(None)
        if manager._started:
            await manager.broker.shutdown()
        await db.dispose()


async def test_shouldbroadcast_is_queued_by_default_and_delivered_on_drain(ctx: Any) -> None:
    app, events, manager, _ = ctx
    driver = app.make("broadcast").driver()
    assert isinstance(driver, LogBroadcaster)

    await events.dispatch(Pinged())
    assert driver.sent == []  # not sent inline — it's on the queue

    await manager.broker.wait_all()  # drain the in-memory broker
    assert len(driver.sent) == 1
    name, channels, _ = driver.sent[0]
    assert name == "pinged"
    assert channels == ["room"]


async def test_shouldbroadcastnow_stays_inline(ctx: Any) -> None:
    app, events, _, _ = ctx
    driver = app.make("broadcast").driver()

    await events.dispatch(PingedNow())
    assert len(driver.sent) == 1  # sent immediately, no queue involved
    assert driver.sent[0][0] == "pinged-now"


async def test_queued_broadcast_inside_a_rolled_back_transaction_is_dropped(ctx: Any) -> None:
    app, events, manager, db = ctx
    driver = app.make("broadcast").driver()

    with pytest.raises(Boom):
        async with db.transaction():
            await events.dispatch(Pinged())
            await manager.broker.wait_all()  # even if it drained mid-tx, nothing was pushed yet
            assert driver.sent == []
            raise Boom

    await manager.broker.wait_all()
    assert driver.sent == []  # rollback dropped the buffered enqueue — never reached the broker


async def test_queued_broadcast_outside_a_transaction_is_immediate_enqueue(ctx: Any) -> None:
    app, events, manager, db = ctx
    driver = app.make("broadcast").driver()

    async with db.transaction():
        pass  # no work buffered — commits trivially

    await events.dispatch(Pinged())
    await manager.broker.wait_all()
    assert len(driver.sent) == 1
