"""Tests for EventDispatcher — Story 1.

FR-002: Dispatch to sync listeners.
FR-003: Dispatch to queued listeners via QueueContract.
FR-004: Multiple listeners with priority ordering.
FR-005: Cross-module listener execution without direct import.
SEC: Events do not serialize sensitive fields when queued.
"""

from __future__ import annotations

import pytest

from arvel.events.listener import Listener, queued

from .conftest import (
    LogRegistration,
    OrderPlaced,
    SendWelcomeEmail,
    SendWelcomeEmailQueued,
    UserRegistered,
)


class TestSyncDispatch:
    """FR-002: Sync listeners execute in the same request lifecycle."""

    async def test_sync_listener_receives_event(self) -> None:
        from arvel.events.dispatcher import EventDispatcher

        dispatcher = EventDispatcher()
        listener = SendWelcomeEmail()
        dispatcher.register(UserRegistered, type(listener))

        event = UserRegistered(user_id="u1", email="a@b.com")
        await dispatcher.dispatch(event)

    async def test_sync_listener_handle_called(self) -> None:
        """Listener's handle() is called with the dispatched event."""
        from arvel.events.dispatcher import EventDispatcher

        dispatcher = EventDispatcher()
        calls: list[UserRegistered] = []

        class TrackingListener(Listener):
            async def handle(self, event: UserRegistered) -> None:
                calls.append(event)

        dispatcher.register(UserRegistered, TrackingListener)
        event = UserRegistered(user_id="u1", email="a@b.com")
        await dispatcher.dispatch(event)

        assert len(calls) == 1
        assert calls[0].user_id == "u1"

    async def test_dispatch_no_listeners_is_noop(self) -> None:
        from arvel.events.dispatcher import EventDispatcher

        dispatcher = EventDispatcher()
        event = UserRegistered(user_id="u1", email="a@b.com")
        await dispatcher.dispatch(event)


class TestQueuedDispatch:
    """FR-003: Queued listeners dispatched via QueueContract."""

    async def test_queued_listener_dispatches_job(self) -> None:
        """When a @queued listener is registered, dispatching the event
        should create a HandleListenerJob and dispatch it to the queue.
        """
        from arvel.events.dispatcher import EventDispatcher

        dispatcher = EventDispatcher()
        dispatcher.register(UserRegistered, SendWelcomeEmailQueued)

        event = UserRegistered(user_id="u1", email="a@b.com")
        await dispatcher.dispatch(event)

    async def test_queued_listener_not_called_synchronously(self) -> None:
        """@queued listeners must not execute inline."""
        from arvel.events.dispatcher import EventDispatcher

        sync_calls: list[UserRegistered] = []

        @queued
        class AsyncOnly(Listener):
            async def handle(self, event: UserRegistered) -> None:
                sync_calls.append(event)

        dispatcher = EventDispatcher()
        dispatcher.register(UserRegistered, AsyncOnly)

        event = UserRegistered(user_id="u1", email="a@b.com")
        await dispatcher.dispatch(event)

        assert len(sync_calls) == 0


class TestPriorityOrdering:
    """FR-004: Multiple listeners execute in priority order."""

    async def test_listeners_execute_in_priority_order(self) -> None:
        from arvel.events.dispatcher import EventDispatcher

        order: list[str] = []

        class HighPriority(Listener):
            async def handle(self, event: UserRegistered) -> None:
                order.append("high")

        class LowPriority(Listener):
            async def handle(self, event: UserRegistered) -> None:
                order.append("low")

        dispatcher = EventDispatcher()
        dispatcher.register(UserRegistered, HighPriority, priority=10)
        dispatcher.register(UserRegistered, LowPriority, priority=100)

        event = UserRegistered(user_id="u1", email="a@b.com")
        await dispatcher.dispatch(event)

        assert order == ["high", "low"]

    async def test_default_priority_is_50(self) -> None:
        from arvel.events.dispatcher import EventDispatcher

        order: list[str] = []

        class Before(Listener):
            async def handle(self, event: UserRegistered) -> None:
                order.append("before")

        class Default(Listener):
            async def handle(self, event: UserRegistered) -> None:
                order.append("default")

        class After(Listener):
            async def handle(self, event: UserRegistered) -> None:
                order.append("after")

        dispatcher = EventDispatcher()
        dispatcher.register(UserRegistered, Before, priority=10)
        dispatcher.register(UserRegistered, Default)
        dispatcher.register(UserRegistered, After, priority=90)

        event = UserRegistered(user_id="u1", email="a@b.com")
        await dispatcher.dispatch(event)

        assert order == ["before", "default", "after"]


class TestCrossModuleDispatch:
    """FR-005: Cross-module listener execution without direct import."""

    async def test_listener_for_different_module_event(self) -> None:
        """A listener registered for an event type from another module
        should execute when that event is dispatched.
        """
        from arvel.events.dispatcher import EventDispatcher

        received: list[OrderPlaced] = []

        class CrossModuleListener(Listener):
            async def handle(self, event: OrderPlaced) -> None:
                received.append(event)

        dispatcher = EventDispatcher()
        dispatcher.register(OrderPlaced, CrossModuleListener)

        event = OrderPlaced(order_id="ord_001", total=42.0)
        await dispatcher.dispatch(event)

        assert len(received) == 1
        assert received[0].order_id == "ord_001"


class TestListenersForQuery:
    """EventDispatcher.listeners_for returns registered listeners."""

    async def test_returns_registered_listeners(self) -> None:
        from arvel.events.dispatcher import EventDispatcher

        dispatcher = EventDispatcher()
        dispatcher.register(UserRegistered, SendWelcomeEmail)
        dispatcher.register(UserRegistered, LogRegistration)

        listeners = dispatcher.listeners_for(UserRegistered)
        assert len(listeners) == 2

    async def test_returns_empty_for_unknown_event(self) -> None:
        from arvel.events.dispatcher import EventDispatcher

        dispatcher = EventDispatcher()
        listeners = dispatcher.listeners_for(OrderPlaced)
        assert listeners == []


class TestDispatchErrorHandling:
    """Sync listener errors propagate to the caller."""

    async def test_listener_error_propagates(self) -> None:
        from arvel.events.dispatcher import EventDispatcher

        class FailingListener(Listener):
            async def handle(self, event: UserRegistered) -> None:
                raise ValueError("listener failed")

        dispatcher = EventDispatcher()
        dispatcher.register(UserRegistered, FailingListener)

        event = UserRegistered(user_id="u1", email="a@b.com")
        with pytest.raises(ValueError, match="listener failed"):
            await dispatcher.dispatch(event)
