"""ConsoleServiceProvider + Application.run + scheduler auto-wire.

Tests for:
 Application.run(name) -> int (programmatic invocation)
 Application.register_command(cmd) (post-construction registration)
 ConsoleServiceProvider.register binds Application in container
 ConsoleServiceProvider.boot collects provider commands (both shapes)
 ServiceProvider.commands return type widened to list[type[Command] | Command]
 SchedulerServiceProvider auto-wires run_command when console Application bound
 Both dispatch_job and run_command auto-wired when both providers registered
 Provider.commands raising is tolerated (skipped with warning)
 B Application.iter_providers public accessor
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import pytest
from arvel.application.application import Application as FrameworkApplication
from arvel.console import Application as ConsoleApplication
from arvel.console import Command, Context
from arvel.providers.service_provider import ServiceProvider

# ─── Test doubles ─────────────────────────────────────────────────────────────


class _HelloCmd(Command):
    name = "hello"
    help = "Say hello"

    def handle(self, ctx: Context) -> int:
        return 0


class _FailingCmd(Command):
    name = "fail"
    help = "Always exits 1"

    def handle(self, ctx: Context) -> int:
        return 1


class _StatefulCmd(Command):
    """Command that needs DI — represents the queue:work shape."""

    name = "stateful"
    help = "Needs a dependency"

    def __init__(self, marker: str) -> None:
        self.marker = marker

    def handle(self, ctx: Context) -> int:
        return 0


class _TypeBackedProvider(ServiceProvider):
    """Returns commands as classes (the stateless built-in shape)."""

    def commands(self) -> list[type[Command] | Command]:
        return [_HelloCmd]


class _InstanceBackedProvider(ServiceProvider):
    """Returns commands as instances (the DI-injected shape)."""

    def commands(self) -> list[type[Command] | Command]:
        return [_StatefulCmd(marker="from-provider")]


class _RaisingProvider(ServiceProvider):
    """commands raises — tests boot-walk tolerance."""

    def commands(self) -> list[type[Command] | Command]:
        msg = "provider commands() failed"
        raise RuntimeError(msg)


class _EmptyProvider(ServiceProvider):
    """commands returns []."""

    def commands(self) -> list[type[Command] | Command]:
        return []


# ─── : Application.run(name) -> int ────────────────────────────


def test_application_run_invokes_command_by_name_returns_exit_code() -> None:
    """run dispatches by name, returns Command.handle exit code."""
    app = ConsoleApplication(commands=[_HelloCmd()])
    code = app.run("hello")
    assert code == 0


def test_application_run_propagates_nonzero_exit_code() -> None:
    """failing command's exit code is returned, not raised."""
    app = ConsoleApplication(commands=[_FailingCmd()])
    code = app.run("fail")
    assert code == 1


def test_application_run_raises_keyerror_on_unknown_command() -> None:
    """unknown command name raises KeyError (no silent fallback)."""
    app = ConsoleApplication(commands=[_HelloCmd()])
    with pytest.raises(KeyError):
        app.run("does-not-exist")


# ─── : Application.register_command(cmd) ────────────────────────────


def test_application_register_command_adds_to_dispatch_table() -> None:
    """register_command adds a Command that run can dispatch."""
    app = ConsoleApplication(commands=[])
    app.register_command(_HelloCmd())
    assert app.run("hello") == 0


def test_application_register_command_overrides_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """re-registering the same name emits a warning; last wins."""
    app = ConsoleApplication(commands=[_HelloCmd()])
    with caplog.at_level(logging.WARNING, logger="arvel.console"):
        app.register_command(_FailingCmd.__new__(_FailingCmd))  # type: ignore[misc]

        # Use a Command whose name COLLIDES with _HelloCmd
        class _Collider(Command):
            name = "hello"
            help = "Different impl"

            def handle(self, ctx: Context) -> int:
                return 42

        app.register_command(_Collider())

    assert any("hello" in record.message for record in caplog.records)
    assert app.run("hello") == 42


# ─── B: Application.iter_providers() ────────────────────────────────


def test_framework_application_iter_providers_yields_registered_instances() -> None:
    """B: public iter_providers exposes every booted provider instance.

    User-listed providers always end up in the chain alongside the framework
    auto-baseline (head: Config/Log/Lang/Database/Http/Scheduler; tail:
    Console). The test asserts the user's providers are present rather than
    asserting an exact chain length, so it stays stable when the baseline
    grows.
    """
    builder = FrameworkApplication.configure(Path.cwd())
    builder.with_environment("testing")
    builder.with_providers([_EmptyProvider, _TypeBackedProvider])
    app = builder.create()

    providers = list(app.iter_providers())
    assert any(isinstance(p, _EmptyProvider) for p in providers)
    assert any(isinstance(p, _TypeBackedProvider) for p in providers)


# ─── / 04 / 05 / : ConsoleServiceProvider ────────────────


def test_console_service_provider_binds_console_application_in_container() -> None:
    """ConsoleServiceProvider.register binds ConsoleApplication."""
    from arvel.console.providers.console_service_provider import ConsoleServiceProvider

    builder = FrameworkApplication.configure(Path.cwd())
    builder.with_environment("testing")
    builder.with_providers([ConsoleServiceProvider])
    app = builder.create()

    assert app.container.bound(ConsoleApplication), (
        "ConsoleServiceProvider.register() must bind ConsoleApplication into the container"
    )


@pytest.mark.asyncio
async def test_console_service_provider_boot_collects_type_backed_commands() -> None:
    """/ : commands returned as TYPES are instantiated and registered."""
    from arvel.console.providers.console_service_provider import ConsoleServiceProvider

    builder = FrameworkApplication.configure(Path.cwd())
    builder.with_environment("testing")
    builder.with_providers([_TypeBackedProvider, ConsoleServiceProvider])
    app = builder.create()
    await app.boot()

    console_app: ConsoleApplication = app.container.make(ConsoleApplication)
    # adispatch (not run) — we're already on a running loop here.
    assert await console_app.adispatch("hello") == 0, (
        "_HelloCmd returned by _TypeBackedProvider as a type must be instantiated and dispatchable"
    )


@pytest.mark.asyncio
async def test_console_service_provider_boot_collects_instance_backed_commands() -> None:
    """/ : commands returned as INSTANCES are registered as-is."""
    from arvel.console.providers.console_service_provider import ConsoleServiceProvider

    builder = FrameworkApplication.configure(Path.cwd())
    builder.with_environment("testing")
    builder.with_providers([_InstanceBackedProvider, ConsoleServiceProvider])
    app = builder.create()
    await app.boot()

    console_app: ConsoleApplication = app.container.make(ConsoleApplication)
    assert await console_app.adispatch("stateful") == 0, (
        "Pre-built _StatefulCmd instance from _InstanceBackedProvider must be registered as-is"
    )


@pytest.mark.asyncio
async def test_console_service_provider_boot_propagates_raising_provider() -> None:
    """A provider whose commands() raises fails boot loudly (no silent drop)."""
    from arvel.application.errors import BootError
    from arvel.console.providers.console_service_provider import ConsoleServiceProvider

    builder = FrameworkApplication.configure(Path.cwd())
    builder.with_environment("testing")
    builder.with_providers([_RaisingProvider, _TypeBackedProvider, ConsoleServiceProvider])
    app = builder.create()

    with pytest.raises(BootError) as excinfo:
        await app.boot()
    assert isinstance(excinfo.value.original, RuntimeError)


# ─── / 07: SchedulerServiceProvider auto-wires run_command ─────────


@pytest.mark.asyncio
async def test_scheduler_auto_wires_run_command_when_console_application_bound() -> None:
    """scheduler kernel's run_command hook resolves the console Application."""
    from arvel.console.providers.console_service_provider import ConsoleServiceProvider
    from arvel.providers.cache_provider import CacheServiceProvider
    from arvel.providers.log_provider import LogServiceProvider
    from arvel.providers.scheduler_provider import SchedulerServiceProvider
    from arvel.scheduling import SchedulerKernel

    builder = FrameworkApplication.configure(Path.cwd())
    builder.with_environment("testing")
    builder.with_providers(
        [
            LogServiceProvider,
            CacheServiceProvider,
            _TypeBackedProvider,
            ConsoleServiceProvider,
            SchedulerServiceProvider,
        ]
    )
    app = builder.create()
    await app.boot()

    kernel: SchedulerKernel = app.container.make(SchedulerKernel)
    run_command = kernel.hooks.run_command
    assert run_command is not None, (
        "SchedulerServiceProvider must auto-wire run_command when console Application is bound"
    )

    # The wired hook must invoke the actual command and complete without raising.
    result = run_command("hello")
    if asyncio.iscoroutine(result):
        await result


@pytest.mark.asyncio
async def test_scheduler_run_command_raises_on_nonzero_exit_code() -> None:
    """non-zero exit code from a scheduled command propagates as RuntimeError."""
    from arvel.console.providers.console_service_provider import ConsoleServiceProvider
    from arvel.providers.cache_provider import CacheServiceProvider
    from arvel.providers.log_provider import LogServiceProvider
    from arvel.providers.scheduler_provider import SchedulerServiceProvider
    from arvel.scheduling import SchedulerKernel

    class _FailingProvider(ServiceProvider):
        def commands(self) -> list[type[Command] | Command]:
            return [_FailingCmd]

    builder = FrameworkApplication.configure(Path.cwd())
    builder.with_environment("testing")
    builder.with_providers(
        [
            LogServiceProvider,
            CacheServiceProvider,
            _FailingProvider,
            ConsoleServiceProvider,
            SchedulerServiceProvider,
        ]
    )
    app = builder.create()
    await app.boot()

    kernel: SchedulerKernel = app.container.make(SchedulerKernel)
    run_command = kernel.hooks.run_command
    assert run_command is not None

    async def _invoke_via_hook() -> None:
        result = run_command("fail")
        if asyncio.iscoroutine(result):
            await result

    with pytest.raises(RuntimeError, match="fail"):
        await _invoke_via_hook()


def test_scheduler_skips_run_command_when_no_console_application_bound() -> None:
    """scheduler defensively returns ``run_command=None`` when nothing
    has bound ``ConsoleApplication`` in the container.

    The auto-baseline always pins ``ConsoleServiceProvider`` last, so
    in normal usage this branch isn't reachable through ``Application.create``.
    The defensive code still exists for tests or specialised hosts that build
    a custom ``FrameworkApplication`` — invoke ``SchedulerServiceProvider``
    directly against an Application stub whose container deliberately lacks
    the ``ConsoleApplication`` binding to exercise it.
    """
    from arvel.providers.cache_provider import CacheServiceProvider
    from arvel.providers.log_provider import LogServiceProvider
    from arvel.providers.scheduler_provider import SchedulerServiceProvider
    from arvel.scheduling import SchedulerKernel

    class _MinimalApp:
        """Just enough of FrameworkApplication to satisfy the provider register pass."""

        def __init__(self) -> None:
            from arvel.container.container import Container

            self.container: Container = Container()

    app: Any = _MinimalApp()
    # The scheduler provider relies on Log + Cache bindings during register().
    LogServiceProvider(app).register()
    CacheServiceProvider(app).register()
    SchedulerServiceProvider(app).register()

    kernel: SchedulerKernel = app.container.make(SchedulerKernel)
    assert kernel.hooks.run_command is None, (
        "run_command must be None when ConsoleApplication is not bound — scheduler "
        "then skips command tasks with reason='no_run_command_callback'"
    )
