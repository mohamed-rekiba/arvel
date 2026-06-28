"""Application — register/boot lifecycle, hook bus, terminating, config, lifespan."""

from __future__ import annotations

from typing import Any

from arvel.kernel import Application, Repository, lifespan, set_application


class RecordingProvider:
    """A minimal duck-typed service provider (the concrete base lands in T1.4)."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self.registered = False
        self.booted = False

    def register(self) -> None:
        self.registered = True
        self.app.singleton("svc", lambda: "S")

    async def boot(self) -> None:
        self.booted = True

    def provides(self) -> list[Any]:
        return []


def test_create_sets_base_path_and_self_bindings() -> None:
    app = Application.configure("/srv/app").create()
    assert app.base_path == "/srv/app"
    assert app.make("app") is app
    set_application(None)


def test_register_runs_register_not_boot() -> None:
    app = Application.configure().with_providers([RecordingProvider]).create()
    provider = app._providers[0]
    assert provider.registered is True
    assert provider.booted is False
    assert app.make("svc") == "S"  # register() bound it
    set_application(None)


async def test_boot_boots_providers_once() -> None:
    app = Application.configure().with_providers([RecordingProvider]).create()
    provider = app._providers[0]
    await app.boot()
    assert provider.booted is True
    assert app.booted is True
    provider.booted = False
    await app.boot()  # idempotent
    assert provider.booted is False
    set_application(None)


async def test_hook_bus_fires_booting_then_booted() -> None:
    app = Application.configure().create()
    events: list[str] = []
    app.on("booting", lambda _a: events.append("booting"))
    app.on("booted", lambda _a: events.append("booted"))
    await app.boot()
    assert events == ["booting", "booted"]
    set_application(None)


async def test_terminating_callbacks_run() -> None:
    app = Application.configure().create()
    calls: list[int] = []
    app.terminating(lambda: calls.append(1))
    app.on("terminating", lambda _a: calls.append(0))
    await app.terminate()
    assert calls == [0, 1]
    set_application(None)


def test_builder_config() -> None:
    app = Application.configure().with_config({"app": {"name": "x"}}).create()
    assert app.config("app.name") == "x"
    assert isinstance(app.config(), Repository)
    set_application(None)


async def test_lifespan_boots_and_terminates() -> None:
    app = Application.configure().with_providers([RecordingProvider]).create()
    terminated: list[int] = []
    app.terminating(lambda: terminated.append(1))
    async with lifespan(app) as running:
        assert running.booted is True
        assert terminated == []
    assert terminated == [1]
    set_application(None)
