"""T3.1 — events: dispatch, halting, wildcards, listener DI, stop-propagation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from arvel.events import Dispatcher, ShouldQueue
from arvel.kernel import Application


@dataclass
class UserRegistered:
    name: str


class RecordingListener:
    seen: list[str] = []

    def handle(self, event: UserRegistered) -> None:
        RecordingListener.seen.append(event.name)


async def test_dispatch_class_event_to_callable() -> None:
    d = Dispatcher()
    got: list[str] = []
    d.listen(UserRegistered, lambda e: got.append(e.name))
    result = await d.dispatch(UserRegistered("ada"))
    assert got == ["ada"]
    assert isinstance(result, list)


async def test_string_event_with_payload() -> None:
    d = Dispatcher()
    got: list[tuple[Any, ...]] = []
    d.listen("user.created", lambda *p: got.append(p))
    await d.dispatch("user.created", 1, 2)
    assert got == [(1, 2)]


async def test_until_halts_on_first_non_none() -> None:
    d = Dispatcher()
    calls: list[int] = []
    d.listen("x", lambda: calls.append(1))  # returns None → continue
    d.listen("x", lambda: "stop")
    d.listen("x", lambda: calls.append(3))  # must not run
    result = await d.until("x")
    assert result == "stop"
    assert calls == [1]


async def test_false_stops_propagation() -> None:
    d = Dispatcher()
    calls: list[int] = []
    d.listen("y", lambda: False)
    d.listen("y", lambda: calls.append(2))
    await d.dispatch("y")
    assert calls == []


async def test_wildcard_listeners() -> None:
    d = Dispatcher()
    got: list[str] = []
    d.listen("order.*", lambda *_p: got.append("wild"))
    await d.dispatch("order.shipped")
    assert got == ["wild"]


async def test_wildcard_listener_receives_event_name_first() -> None:
    d = Dispatcher()
    seen: list[tuple[object, ...]] = []
    d.listen("user.*", lambda *a: seen.append(a))
    await d.dispatch("user.created", {"id": 7})
    # a wildcard handler gets (event_name, *payload) so it can tell events apart
    assert seen == [("user.created", {"id": 7})]


async def test_class_listener_resolved_via_container() -> None:
    app = Application()
    d = Dispatcher(app)
    RecordingListener.seen = []
    d.listen(UserRegistered, RecordingListener)
    await d.dispatch(UserRegistered("bob"))
    assert RecordingListener.seen == ["bob"]


async def test_async_listener_awaited() -> None:
    d = Dispatcher()
    got: list[str] = []

    async def listener(e: UserRegistered) -> None:
        got.append(e.name)

    d.listen(UserRegistered, listener)
    await d.dispatch(UserRegistered("cat"))
    assert got == ["cat"]


async def test_forget() -> None:
    d = Dispatcher()
    got: list[int] = []
    d.listen("z", lambda: got.append(1))
    d.forget("z")
    await d.dispatch("z")
    assert got == []


async def test_should_queue_listener_enqueued_when_queue_bound() -> None:
    """A2: a ShouldQueue listener is enqueued via the container-bound `queue_dispatcher` seam
    (not inline) — a spy dispatcher proves it was actually called, awaited, with the right args."""
    app = Application()
    pushed: list[Any] = []

    async def fake_queue_dispatcher(listener: Any, args: tuple[Any, ...]) -> None:
        pushed.append((listener, args))

    app.instance("queue_dispatcher", fake_queue_dispatcher)
    d = Dispatcher(app)

    class QueuedListener(ShouldQueue):
        def handle(self, event: UserRegistered) -> None:  # pragma: no cover - must not run inline
            raise AssertionError("should have been queued")

    d.listen(UserRegistered, QueuedListener)
    await d.dispatch(UserRegistered("dan"))
    assert pushed == [(QueuedListener, (UserRegistered("dan"),))]


async def test_non_queued_listener_runs_inline_even_with_queue_bound() -> None:
    """A non-ShouldQueue listener always runs inline, even when a `queue_dispatcher` is bound."""
    app = Application()
    pushed: list[Any] = []

    async def fake_queue_dispatcher(listener: Any, args: tuple[Any, ...]) -> None:
        pushed.append((listener, args))

    app.instance("queue_dispatcher", fake_queue_dispatcher)
    d = Dispatcher(app)
    ran: list[str] = []

    class PlainListener:
        def handle(self, event: UserRegistered) -> None:
            ran.append(event.name)

    d.listen(UserRegistered, PlainListener)
    await d.dispatch(UserRegistered("eve"))
    assert ran == ["eve"]
    assert pushed == []


async def test_should_queue_listener_runs_inline_without_queue_dispatcher_bound() -> None:
    """Documented fallback: no `queue_dispatcher` bound (no queue provider registered) -> a
    ShouldQueue listener still runs, inline, rather than silently vanishing."""
    d = Dispatcher(Application())
    ran: list[str] = []

    class QueuedListener(ShouldQueue):
        def handle(self, event: UserRegistered) -> None:
            ran.append(event.name)

    d.listen(UserRegistered, QueuedListener)
    await d.dispatch(UserRegistered("finn"))
    assert ran == ["finn"]
