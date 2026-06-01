"""EventDispatcher routes ShouldBroadcast events to Broadcast.send."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest


@pytest.mark.asyncio
async def test_dispatcher_invokes_broadcast_for_should_broadcast_events() -> None:
    """dispatching ShouldBroadcast event calls Broadcast.send exactly once."""
    from arvel.broadcasting import ShouldBroadcast
    from arvel.broadcasting.config import BroadcastConfig, BroadcastDriver
    from arvel.broadcasting.manager import BroadcastManager
    from arvel.events.dispatcher import EventDispatcher
    from arvel.events.event import Event
    from arvel.facades.broadcast import Broadcast

    calls: list[tuple[Sequence[str], str, dict[str, Any]]] = []

    class _SpyBroadcaster:
        async def broadcast(
            self,
            channels: Sequence[str],
            event: str,
            payload: dict[str, Any],
            *,
            except_socket_id: str | None = None,
        ) -> None:
            del except_socket_id
            calls.append((list(channels), event, payload))

    class _SpyManager(BroadcastManager):
        def driver(self, name: str | None = None) -> Any:
            return _SpyBroadcaster()

    Broadcast.set_manager(_SpyManager(BroadcastConfig(default=BroadcastDriver.NULL)))
    try:

        class OrderShipped(Event, ShouldBroadcast):
            order_id: int = 0

            def broadcast_on(self) -> Sequence[str]:
                return ["orders"]

        dispatcher = EventDispatcher()
        await dispatcher.dispatch(OrderShipped(order_id=42))
    finally:
        Broadcast.set_manager(None)

    assert len(calls) == 1
    channels, event_name, payload = calls[0]
    assert channels == ["orders"]
    assert event_name == "OrderShipped"
    assert payload == {"order_id": 42}


@pytest.mark.asyncio
async def test_dispatcher_does_not_broadcast_plain_events() -> None:
    """regular events don't reach Broadcast.send."""
    from arvel.broadcasting.config import BroadcastConfig, BroadcastDriver
    from arvel.broadcasting.manager import BroadcastManager
    from arvel.events.dispatcher import EventDispatcher
    from arvel.events.event import Event
    from arvel.facades.broadcast import Broadcast

    seen: list[Any] = []

    class _SpyBroadcaster:
        async def broadcast(self, *a: Any, **kw: Any) -> None:
            seen.append((a, kw))

    class _SpyManager(BroadcastManager):
        def driver(self, name: str | None = None) -> Any:
            return _SpyBroadcaster()

    Broadcast.set_manager(_SpyManager(BroadcastConfig(default=BroadcastDriver.NULL)))
    try:

        class PlainEvent(Event):
            pass

        dispatcher = EventDispatcher()
        await dispatcher.dispatch(PlainEvent())
    finally:
        Broadcast.set_manager(None)

    assert not seen


@pytest.mark.asyncio
async def test_dispatcher_swallows_broadcaster_errors() -> None:
    """broadcaster failures don't break sync listeners."""
    from arvel.broadcasting import ShouldBroadcast
    from arvel.broadcasting.config import BroadcastConfig, BroadcastDriver
    from arvel.broadcasting.exceptions import BroadcastDriverError
    from arvel.broadcasting.manager import BroadcastManager
    from arvel.events.dispatcher import EventDispatcher
    from arvel.events.event import Event
    from arvel.facades.broadcast import Broadcast

    class _Boom:
        async def broadcast(self, *a: Any, **kw: Any) -> None:
            raise BroadcastDriverError("boom")

    class _Manager(BroadcastManager):
        def driver(self, name: str | None = None) -> Any:
            return _Boom()

    Broadcast.set_manager(_Manager(BroadcastConfig(default=BroadcastDriver.NULL)))
    try:

        class _Evt(Event, ShouldBroadcast):
            def broadcast_on(self) -> Sequence[str]:
                return ["x"]

        dispatcher = EventDispatcher()
        await dispatcher.dispatch(_Evt())  # MUST NOT raise
    finally:
        Broadcast.set_manager(None)
