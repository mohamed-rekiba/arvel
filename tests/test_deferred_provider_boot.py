"""Item 2 / ch 03 — a deferred provider triggered AFTER the app booted must still run boot()
(previously register() ran but boot() was silently skipped, since the boot loop had finished)."""

from __future__ import annotations

from typing import Any

from arvel.kernel.application import Application
from arvel.kernel.service_provider import ServiceProvider


def _make_provider(events: list[str]) -> type[ServiceProvider]:
    class P(ServiceProvider):
        def provides(self) -> list[Any]:
            return ["thing"]

        def register(self) -> None:
            events.append("register")
            self.app.instance("thing", object())

        def boot(self) -> None:  # sync boot
            events.append("boot")

    return P


async def test_deferred_provider_boots_when_triggered_after_boot() -> None:
    events: list[str] = []
    app = Application.configure().create()
    app.register_deferred(_make_provider(events)(app))
    await app.boot()
    assert events == []  # not registered/booted until its contract is resolved
    app.make("thing")  # trigger
    assert events == ["register", "boot"]


async def test_deferred_provider_not_triggered_stays_dormant() -> None:
    events: list[str] = []
    app = Application.configure().create()
    app.register_deferred(_make_provider(events)(app))
    await app.boot()
    assert events == []  # never resolved → never registered/booted
