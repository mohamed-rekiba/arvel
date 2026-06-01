"""ServiceProvider base."""

from __future__ import annotations

import inspect


def test_service_provider_init_stores_app() -> None:
    from arvel import Application, ServiceProvider

    class P(ServiceProvider): ...

    app = Application()
    p = P(app)
    assert p.app is app


def test_register_is_sync_default_noop() -> None:
    from arvel import ServiceProvider

    sig = inspect.signature(ServiceProvider.register)
    assert not inspect.iscoroutinefunction(ServiceProvider.register)
    assert list(sig.parameters) == ["self"]


def test_boot_is_async_default_noop() -> None:
    from arvel import ServiceProvider

    assert inspect.iscoroutinefunction(ServiceProvider.boot)


def test_shutdown_is_async_default_noop() -> None:
    from arvel import ServiceProvider

    assert inspect.iscoroutinefunction(ServiceProvider.shutdown)


def test_commands_and_provides_defaults() -> None:
    from arvel import Application, ServiceProvider

    class P(ServiceProvider): ...

    app = Application()
    p = P(app)
    assert p.commands() == []
    assert p.provides() == []
