"""Application kernel — fluent builder + two-pass boot lifecycle."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_configure_returns_builder(tmp_path: Path) -> None:
    from arvel import Application, ApplicationBuilder

    builder = Application.configure(tmp_path)
    assert isinstance(builder, ApplicationBuilder)


def test_builder_create_returns_application(tmp_path: Path) -> None:
    from arvel import Application

    app = Application.configure(tmp_path).with_environment("testing").create()
    assert isinstance(app, Application)
    assert app.environment() == "testing"


def test_application_binds_itself_in_its_container(tmp_path: Path) -> None:
    from arvel import Application

    app = Application.configure(tmp_path).with_environment("testing").create()
    assert app.container.make(Application) is app


async def test_two_pass_lifecycle_register_before_any_boot(tmp_path: Path) -> None:
    from arvel import Application, ServiceProvider

    order: list[str] = []

    class P1(ServiceProvider):
        def register(self) -> None:
            order.append("p1.register")

        async def boot(self) -> None:
            order.append("p1.boot")

    class P2(ServiceProvider):
        def register(self) -> None:
            order.append("p2.register")

        async def boot(self) -> None:
            order.append("p2.boot")

    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([P1, P2])
        .create()
    )
    await app.boot()
    assert order == ["p1.register", "p2.register", "p1.boot", "p2.boot"]
    await app.shutdown()


def test_provider_raising_in_register_yields_boot_error_at_create(tmp_path: Path) -> None:
    from arvel import Application, BootError, ServiceProvider

    class Broken(ServiceProvider):
        def register(self) -> None:
            raise RuntimeError("nope")

    # register() now runs eagerly create() so container bindings are
    # available before await app.boot(). Failures surface here, not later.
    with pytest.raises(BootError) as excinfo:
        Application.configure(tmp_path).with_environment("testing").with_providers(
            [Broken]
        ).create()
    assert excinfo.value.provider is Broken


async def test_boot_retry_after_partial_failure_does_not_reboot_providers(
    tmp_path: Path,
) -> None:
    """A failed boot can be retried; already-booted providers don't run twice."""
    from arvel import Application, ServiceProvider

    boots: list[str] = []

    class Ok(ServiceProvider):
        async def boot(self) -> None:
            boots.append("ok")

    class Flaky(ServiceProvider):
        attempts = 0

        async def boot(self) -> None:
            Flaky.attempts += 1
            if Flaky.attempts == 1:
                raise RuntimeError("transient")

    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([Ok, Flaky])
        .create()
    )

    with pytest.raises(Exception, match="transient"):
        await app.boot()

    await app.boot()  # retry succeeds
    assert boots == ["ok"], "Ok.boot() must run exactly once across the failed + retried boot"
    await app.shutdown()


async def test_shutdown_tears_down_partially_booted_providers(tmp_path: Path) -> None:
    """A boot that fails partway still leaves a usable shutdown for what booted."""
    from arvel import Application, ServiceProvider

    events: list[str] = []

    class Ok(ServiceProvider):
        async def boot(self) -> None:
            events.append("ok.boot")

        async def shutdown(self) -> None:
            events.append("ok.shutdown")

    class Boom(ServiceProvider):
        async def boot(self) -> None:
            raise RuntimeError("kaboom")

        async def shutdown(self) -> None:
            events.append("boom.shutdown")  # must NOT run: never booted

    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([Ok, Boom])
        .create()
    )

    with pytest.raises(Exception, match="kaboom"):
        await app.boot()

    # _booted never flipped true, but Ok booted and must be torn down.
    await app.shutdown()
    assert events == ["ok.boot", "ok.shutdown"]


async def test_shutdown_runs_in_reverse_order(tmp_path: Path) -> None:
    from arvel import Application, ServiceProvider

    order: list[str] = []

    class P1(ServiceProvider):
        async def shutdown(self) -> None:
            order.append("p1.shutdown")

    class P2(ServiceProvider):
        async def shutdown(self) -> None:
            order.append("p2.shutdown")

    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([P1, P2])
        .create()
    )
    await app.boot()
    await app.shutdown()
    assert order == ["p2.shutdown", "p1.shutdown"]


def test_with_environment_sets_environment(tmp_path: Path) -> None:
    from arvel import Application

    app = Application.configure(tmp_path).with_environment("production").create()
    assert app.environment() == "production"


async def test_boot_logs_connected_services_and_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from arvel import Application
    from arvel.observability.provider import ObservabilityServiceProvider
    from arvel.services import BaseService, HealthResult, HealthStatus
    from arvel.testing.observability import FakeObservability

    # Stop the observability provider from re-bootstrapping the OTel SDK mid-boot,
    # which would replace the FakeObservability logger provider we're capturing on.
    async def _noop_boot(self: ObservabilityServiceProvider) -> None:
        return

    monkeypatch.setattr(ObservabilityServiceProvider, "boot", _noop_boot)

    class DummyService(BaseService):
        name = "dummy"

        async def health_check(self) -> HealthResult:
            return HealthResult(status=HealthStatus.healthy)

    app = Application.configure(tmp_path).with_environment("testing").create()
    app.register_service(DummyService())

    with FakeObservability() as obs:
        await app.boot()

    obs.assert_logged("service.connected", service="dummy")
    obs.assert_logged("app.boot.complete")
    await app.shutdown()


# Baseline provider auto-registration


def test_baseline_providers_register_without_user_list(tmp_path: Path) -> None:
    """Calling ``.create()`` with no user providers still registers the
    framework baseline so commands like ``arvel migrate`` find their bindings.
    """
    from arvel import Application
    from arvel.console import Application as ConsoleApplication
    from sqlalchemy.ext.asyncio import AsyncEngine

    app = Application.configure(tmp_path).with_environment("testing").create()

    # DatabaseServiceProvider runs → AsyncEngine resolvable.
    engine = app.container.make(AsyncEngine)
    assert isinstance(engine, AsyncEngine)

    # ConsoleServiceProvider runs → console Application resolvable.
    console_app = app.container.make(ConsoleApplication)
    assert isinstance(console_app, ConsoleApplication)


def test_console_service_provider_is_always_last(tmp_path: Path) -> None:
    """Even when the user pins ``ConsoleServiceProvider`` mid-chain, the
    framework moves it to the end so its ``boot()`` sees every other provider.
    """
    from arvel import Application, ServiceProvider
    from arvel.console.providers.console_service_provider import ConsoleServiceProvider

    class TrailingProvider(ServiceProvider):
        pass

    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([ConsoleServiceProvider, TrailingProvider])
        .create()
    )

    classes = app._provider_classes  # pyright: ignore[reportPrivateUsage]
    assert classes[-1] is ConsoleServiceProvider
    assert classes.count(ConsoleServiceProvider) == 1


def test_user_listed_baseline_provider_is_deduplicated(tmp_path: Path) -> None:
    """Listing a HEAD provider in the user list must not double-register it."""
    from arvel import Application
    from arvel.providers import DatabaseServiceProvider

    app = (
        Application.configure(tmp_path)
        .with_environment("testing")
        .with_providers([DatabaseServiceProvider])
        .create()
    )

    classes = app._provider_classes  # pyright: ignore[reportPrivateUsage]
    assert classes.count(DatabaseServiceProvider) == 1
