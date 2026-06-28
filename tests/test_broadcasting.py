"""Broadcasting (doc 11) — BroadcastManager + dispatcher integration for ShouldBroadcast."""

from __future__ import annotations

from arvel.broadcasting import BroadcastManager, LogBroadcaster, channels_for, event_name
from arvel.events.dispatcher import Dispatcher, ShouldBroadcast
from arvel.kernel.container import Container


class OrderShipped(ShouldBroadcast):
    def broadcast_on(self) -> list[str]:
        return ["orders", "private-user.1"]

    def broadcast_as(self) -> str:
        return "order.shipped"


async def test_manager_records_via_log_driver() -> None:
    manager = BroadcastManager()
    assert manager.default_driver() == "log"
    await manager.broadcast(OrderShipped())
    driver = manager.driver()
    assert isinstance(driver, LogBroadcaster)
    name, channels, _ = driver.sent[0]
    assert name == "order.shipped"
    assert channels == ["orders", "private-user.1"]


async def test_dispatcher_broadcasts_shouldbroadcast_events() -> None:
    container = Container()
    manager = BroadcastManager()
    container.instance("broadcast", manager)
    dispatcher = Dispatcher(container)

    await dispatcher.dispatch(OrderShipped())
    assert len(manager.driver().sent) == 1


def test_channel_and_name_helpers_default() -> None:
    class Plain: ...

    assert channels_for(Plain()) == []
    assert event_name(Plain()) == "Plain"
