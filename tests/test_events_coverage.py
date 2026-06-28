"""Coverage — dispatcher wildcards, subscribe map, queued + broadcast markers (doc 11)."""

from __future__ import annotations

from typing import Any

from arvel.events import Dispatcher, ShouldBroadcast, ShouldQueue


async def test_wildcard_listeners() -> None:
    dispatcher = Dispatcher()
    seen: list[str] = []
    dispatcher.listen("user.*", lambda *a: seen.append("hit"))
    await dispatcher.dispatch("user.created")
    assert seen == ["hit"]


async def test_subscribe_via_listen_map() -> None:
    fired: list[str] = []

    class Subscriber:
        listen = {"order.placed": [lambda *a: fired.append("placed")]}

    dispatcher = Dispatcher()
    dispatcher.subscribe(Subscriber())
    await dispatcher.dispatch("order.placed")
    assert fired == ["placed"]


async def test_until_halts_on_first_non_none() -> None:
    dispatcher = Dispatcher()
    dispatcher.listen("e", lambda *a: None)
    dispatcher.listen("e", lambda *a: "stop")
    assert await dispatcher.until("e") == "stop"


class _Container:
    def __init__(self, **services: Any) -> None:
        self._services = services

    def bound(self, key: str) -> bool:
        return key in self._services

    def make(self, key: Any) -> Any:
        return self._services[key]


async def test_should_queue_listener_is_pushed() -> None:
    class FakeQueue:
        def __init__(self) -> None:
            self.pushed: list[Any] = []

        def push(self, listener: Any, args: Any) -> None:
            self.pushed.append(listener)

    queue = FakeQueue()

    class QueuedListener(ShouldQueue):
        def handle(self, *args: Any) -> None:  # should NOT run inline
            raise AssertionError("should have been queued")

    dispatcher = Dispatcher(_Container(queue=queue))
    dispatcher.listen("e", QueuedListener)
    await dispatcher.dispatch("e")
    assert queue.pushed == [QueuedListener]


async def test_should_broadcast_event() -> None:
    class FakeBroadcaster:
        def __init__(self) -> None:
            self.got: Any = None

        async def broadcast(self, event: Any) -> None:
            self.got = event

    broadcaster = FakeBroadcaster()

    class Pinged(ShouldBroadcast):
        pass

    dispatcher = Dispatcher(_Container(broadcast=broadcaster))
    event = Pinged()
    await dispatcher.dispatch(event)
    assert broadcaster.got is event
