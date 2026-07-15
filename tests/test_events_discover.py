"""Events — auto-discovery registers listeners by their handle(self, event: X) hint."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

from arvel.events import Dispatcher
from arvel.events.provider import EventServiceProvider, discover_listeners


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


def test_discover_listeners_scans_a_folder(tmp_path: Path) -> None:
    # a temp app/listeners/ package with a class listener + a non-listener class
    (tmp_path / "app" / "listeners").mkdir(parents=True)
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "listeners" / "__init__.py").write_text("")
    (tmp_path / "app" / "listeners" / "welcome.py").write_text(
        "class Registered: ...\n"
        "class SendWelcome:\n"
        "    async def handle(self, event: Registered) -> None: ...\n"
    )
    sys.path.insert(0, str(tmp_path))
    try:
        found = discover_listeners(SimpleNamespace(base_path=str(tmp_path)), ["app/listeners"])
        assert [c.__name__ for c in found] == ["SendWelcome"]  # the non-listener class is skipped
    finally:
        sys.path.remove(str(tmp_path))
        for mod in [m for m in list(sys.modules) if m == "app" or m.startswith("app.")]:
            del sys.modules[mod]


def test_discover_listeners_skips_a_missing_dir() -> None:
    found = discover_listeners(SimpleNamespace(base_path="/nonexistent"), ["app/listeners"])
    assert found == []


def test_boot_skips_when_discovery_disabled() -> None:
    made: list[str] = []
    app = SimpleNamespace(
        base_path=".",
        config=lambda key, default=None: False if key == "events.discover" else default,
        make=made.append,  # boot must not resolve "events" when discovery is off
    )
    EventServiceProvider(app).boot()
    assert made == []
