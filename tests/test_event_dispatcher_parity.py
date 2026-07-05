"""Event-dispatcher parity: has_listeners and the deferred-event trio push/flush/forget_pushed
were absent. has_listeners honors direct + wildcard registrations and accepts a class, string, or instance."""

from __future__ import annotations

from arvel.events.dispatcher import Dispatcher


class OrderShipped:
    pass


def test_has_listeners_direct_and_wildcard() -> None:
    d = Dispatcher()
    d.listen("user.created", lambda *a: None)
    d.listen("user.*", lambda *a: None)
    assert d.has_listeners("user.created") is True  # direct (+ wildcard)
    assert d.has_listeners("user.updated") is True  # wildcard match only
    assert d.has_listeners("order.placed") is False


def test_has_listeners_class_and_instance() -> None:
    d = Dispatcher()
    d.listen(OrderShipped, lambda e: None)
    assert d.has_listeners(OrderShipped) is True  # by class
    assert d.has_listeners(OrderShipped()) is True  # by instance
    assert d.has_listeners(object) is False


async def test_push_flush_forget_pushed() -> None:
    d = Dispatcher()
    received: list[tuple] = []
    d.listen("report.ready", lambda *a: received.append(a))

    d.push("report.ready", {"id": 1})
    d.push("report.ready", {"id": 2})
    assert received == []  # deferred — nothing fired yet

    await d.flush("report.ready")
    assert received == [({"id": 1},), ({"id": 2},)]

    await d.flush("report.ready")  # already drained → no double-fire
    assert len(received) == 2

    d.push("temp.event")
    d.forget_pushed()
    await d.flush("temp.event")
    assert len(received) == 2  # forget_pushed discarded it
