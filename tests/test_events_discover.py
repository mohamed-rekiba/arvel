"""Events — auto-discovery registers listeners by their handle(self, event: X) hint."""

from __future__ import annotations

from typing import ClassVar

from arvel.events import Dispatcher


class UserRegistered:
    pass


class OrderShipped:
    pass


class SendWelcome:
    seen: ClassVar[list] = []

    async def handle(self, event: UserRegistered) -> None:
        SendWelcome.seen.append(event)


class NotifyWarehouse:
    seen: ClassVar[list] = []

    async def handle(self, event: OrderShipped) -> None:
        NotifyWarehouse.seen.append(event)


class NoHandle:
    pass


class NoAnnotation:
    async def handle(self, event) -> None:  # type: ignore[no-untyped-def]
        ...


async def test_discover_registers_by_hint() -> None:
    SendWelcome.seen.clear()
    NotifyWarehouse.seen.clear()
    d = Dispatcher()
    d.discover([SendWelcome, NotifyWarehouse])

    await d.dispatch(UserRegistered())
    await d.dispatch(OrderShipped())

    assert len(SendWelcome.seen) == 1
    assert len(NotifyWarehouse.seen) == 1
    # cross-wiring didn't happen
    await d.dispatch(UserRegistered())
    assert len(NotifyWarehouse.seen) == 1


async def test_discover_skips_listeners_without_a_usable_handle() -> None:
    d = Dispatcher()
    d.discover([NoHandle, NoAnnotation])  # must not raise
    assert d._listeners == {}  # nothing registered
