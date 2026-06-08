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

    @pytest.mark.asyncio
    async def test_queued_listener_enqueues_and_does_not_run_inline(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When a queue is configured, the listener is enqueued, not run inline."""
        from arvel.events.listener_job import ListenerJob
        from arvel.facades.bus import Bus

        dispatcher = EventDispatcher()
        ran_inline: list[int] = []
        dispatched: list[ListenerJob] = []

        class QueuedListener(Listener[_OrderEvent], ShouldQueue):
            async def handle(self, event: _OrderEvent) -> None:
                ran_inline.append(event.order_id)

        async def fake_dispatch(job: ListenerJob) -> None:
            dispatched.append(job)

        monkeypatch.setattr(Bus, "manager", object())
        monkeypatch.setattr(Bus, "dispatch", staticmethod(fake_dispatch))

        dispatcher.listen(_OrderEvent, QueuedListener)
        await dispatcher.dispatch(_OrderEvent(order_id=8))

        assert ran_inline == []
        assert len(dispatched) == 1
        assert dispatched[0].listener_class_key.endswith("QueuedListener")

    @pytest.mark.asyncio
    async def test_enqueue_failure_is_logged_not_swallowed_or_inline(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A broker failure logs and is swallowed at the loop level — never run inline."""
        from arvel.facades.bus import Bus
        from arvel.queue.job import Job
        from arvel.testing.observability import FakeObservability

        dispatcher = EventDispatcher()
        ran_inline: list[int] = []

        class QueuedListener(Listener[_OrderEvent], ShouldQueue):
            async def handle(self, event: _OrderEvent) -> None:
                ran_inline.append(event.order_id)

        async def boom(job: Job) -> None:
            raise RuntimeError("broker down")

        monkeypatch.setattr(Bus, "manager", object())
        monkeypatch.setattr(Bus, "dispatch", staticmethod(boom))

        dispatcher.listen(_OrderEvent, QueuedListener)
        with FakeObservability() as obs:
            # The publish loop must not raise even though the enqueue failed.
            await dispatcher.dispatch(_OrderEvent(order_id=9))

        assert ran_inline == []
        failures = [r for r in obs.log_records if r.body == "queued_listener_enqueue_failed"]
        assert len(failures) == 1
