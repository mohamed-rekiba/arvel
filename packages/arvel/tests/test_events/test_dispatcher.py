"""Tests for EventDispatcher."""

from __future__ import annotations

import pytest
from arvel.events.dispatcher import EventDispatcher
from arvel.events.event import Event
from arvel.events.listener import Listener
from arvel.events.should_queue import ShouldQueue


class _OrderEvent(Event):
    order_id: int


class _UserEvent(Event):
    user_id: int


class TestEventDispatcher:
    """listen() registers a listener."""

    def test_listen_registers_listener(self) -> None:
        dispatcher = EventDispatcher()
        results: list[int] = []

        class Cap(Listener[_OrderEvent]):
            async def handle(self, event: _OrderEvent) -> None:
                results.append(event.order_id)

        dispatcher.listen(_OrderEvent, Cap)
        assert len(dispatcher.listeners(_OrderEvent)) == 1

    def test_listen_is_idempotent(self) -> None:
        """registering the same pair twice is idempotent."""
        dispatcher = EventDispatcher()

        class Cap2(Listener[_OrderEvent]):
            async def handle(self, event: _OrderEvent) -> None:
                pass

        dispatcher.listen(_OrderEvent, Cap2)
        dispatcher.listen(_OrderEvent, Cap2)
        assert len(dispatcher.listeners(_OrderEvent)) == 1

    @pytest.mark.asyncio
    async def test_dispatch_calls_all_listeners(self) -> None:
        """dispatch calls all registered listeners."""
        dispatcher = EventDispatcher()
        seen: list[str] = []

        class L1(Listener[_OrderEvent]):
            async def handle(self, event: _OrderEvent) -> None:
                seen.append("L1")

        class L2(Listener[_OrderEvent]):
            async def handle(self, event: _OrderEvent) -> None:
                seen.append("L2")

        dispatcher.listen(_OrderEvent, L1)
        dispatcher.listen(_OrderEvent, L2)
        await dispatcher.dispatch(_OrderEvent(order_id=1))
        assert seen == ["L1", "L2"]

    @pytest.mark.asyncio
    async def test_listener_error_does_not_stop_others(self) -> None:
        """listener error must not prevent other listeners."""
        dispatcher = EventDispatcher()
        seen: list[str] = []

        class Fail(Listener[_OrderEvent]):
            async def handle(self, event: _OrderEvent) -> None:
                raise RuntimeError("boom")

        class Ok(Listener[_OrderEvent]):
            async def handle(self, event: _OrderEvent) -> None:
                seen.append("ok")

        dispatcher.listen(_OrderEvent, Fail)
        dispatcher.listen(_OrderEvent, Ok)
        await dispatcher.dispatch(_OrderEvent(order_id=2))
        assert "ok" in seen

    @pytest.mark.asyncio
    async def test_dispatch_with_no_listeners_is_a_noop(self) -> None:
        dispatcher = EventDispatcher()
        await dispatcher.dispatch(_OrderEvent(order_id=3))  # should not raise

    @pytest.mark.asyncio
    async def test_dispatch_only_calls_matching_event_listeners(self) -> None:
        dispatcher = EventDispatcher()
        called: list[str] = []

        class OrderListener(Listener[_OrderEvent]):
            async def handle(self, event: _OrderEvent) -> None:
                called.append("order")

        class UserListener(Listener[_UserEvent]):
            async def handle(self, event: _UserEvent) -> None:
                called.append("user")

        dispatcher.listen(_OrderEvent, OrderListener)
        dispatcher.listen(_UserEvent, UserListener)
        await dispatcher.dispatch(_OrderEvent(order_id=5))
        assert called == ["order"]

    @pytest.mark.asyncio
    async def test_should_queue_listener_degrades_gracefully_without_bus(self) -> None:
        """ShouldQueue falls back to inline when Bus not bound."""
        dispatcher = EventDispatcher()
        seen: list[int] = []

        class QueuedListener(Listener[_OrderEvent], ShouldQueue):
            async def handle(self, event: _OrderEvent) -> None:
                seen.append(event.order_id)

        dispatcher.listen(_OrderEvent, QueuedListener)
        # Bus is not bound — should execute inline, not raise
        await dispatcher.dispatch(_OrderEvent(order_id=7))
        assert seen == [7]
