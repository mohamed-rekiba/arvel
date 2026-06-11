"""Unified programmatic dispatch: adispatch drives the real Typer callback.

Before C2, Application.run() called handle() directly, so the ~all commands
whose real work is deferred via schedule_async (and whose handle() raises
NotImplementedError) couldn't be scheduled or called programmatically, and no
flags could be passed. adispatch() now runs the command's register()-installed
callback through Typer and awaits the deferred coroutine.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, ClassVar, cast
from unittest.mock import MagicMock

import pytest
import typer
from arvel.console import Application, Command, Context, schedule_async

if TYPE_CHECKING:
    from arvel.application import Application as FrameworkApplication
    from arvel.scheduling import SchedulerKernel


class _SyncFail(Command):
    name: ClassVar[str] = "sync:fail"

    def handle(self, ctx: Context) -> int:
        return 7


class _AsyncWork(Command):
    """Defers real work via schedule_async, like every real async command."""

    name: ClassVar[str] = "async:work"
    ran: ClassVar[list[str]] = []

    def register(self, app: typer.Typer) -> None:
        def _cb() -> None:
            async def _work() -> None:
                self.__class__.ran.append("worked")

            schedule_async(_work())

        app.command(name=self.name)(_cb)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError


class _AsyncExit(Command):
    name: ClassVar[str] = "async:exit"

    def register(self, app: typer.Typer) -> None:
        def _cb() -> None:
            async def _work() -> None:
                raise typer.Exit(code=3)

            schedule_async(_work())

        app.command(name=self.name)(_cb)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError


class _FlagCmd(Command):
    name: ClassVar[str] = "flag:cmd"
    seen: ClassVar[list[bool]] = []

    def register(self, app: typer.Typer) -> None:
        def _cb(*, force: Annotated[bool, typer.Option("--force")] = False) -> None:
            async def _work() -> None:
                self.__class__.seen.append(force)

            schedule_async(_work())

        app.command(name=self.name)(_cb)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError


async def test_adispatch_runs_deferred_async_coroutine() -> None:
    _AsyncWork.ran.clear()
    app = Application(commands=[_AsyncWork()])
    code = await app.adispatch("async:work")
    assert code == 0
    assert _AsyncWork.ran == ["worked"]


async def test_adispatch_captures_exit_code_from_deferred_coroutine() -> None:
    app = Application(commands=[_AsyncExit()])
    assert await app.adispatch("async:exit") == 3


async def test_adispatch_parses_flags() -> None:
    _FlagCmd.seen.clear()
    app = Application(commands=[_FlagCmd()])

    assert await app.adispatch("flag:cmd", ["--force"]) == 0
    assert await app.adispatch("flag:cmd") == 0
    assert _FlagCmd.seen == [True, False]


async def test_adispatch_returns_sync_handle_exit_code() -> None:
    app = Application(commands=[_SyncFail()])
    assert await app.adispatch("sync:fail") == 7


async def test_adispatch_unknown_name_raises_keyerror() -> None:
    app = Application(commands=[_SyncFail()])
    with pytest.raises(KeyError):
        await app.adispatch("nope")


async def test_call_forwards_flags_to_target() -> None:
    _FlagCmd.seen.clear()

    class _Caller(Command):
        name: ClassVar[str] = "caller"

        def handle(self, ctx: Context) -> int:
            raise NotImplementedError

    framework_app = MagicMock()
    console_app = Application(commands=[_FlagCmd(), _Caller()])
    framework_app.container.make.return_value = console_app

    caller = _Caller()
    caller.app = framework_app

    code = await caller.call("flag:cmd", "--force")
    assert code == 0
    assert _FlagCmd.seen == [True]


# ── Scheduler hook: Laravel-style "name --flags" splitting through adispatch ──


class _SchedApp:
    def __init__(self, container: object) -> None:
        self.container = container


def _make_kernel_with_console(console_app: Application) -> SchedulerKernel:
    from arvel.console import Application as ConsoleApplication
    from arvel.container import Container
    from arvel.providers.scheduler_provider import SchedulerServiceProvider
    from arvel.scheduling import SchedulerKernel as _Kernel

    container = Container()
    container.instance(ConsoleApplication, console_app)
    provider = SchedulerServiceProvider(cast("FrameworkApplication", _SchedApp(container)))
    provider.register()
    return container.make(_Kernel)


async def test_scheduler_command_splits_flags_and_dispatches() -> None:
    _FlagCmd.seen.clear()
    kernel = _make_kernel_with_console(Application(commands=[_FlagCmd()]))
    # register() built the kernel with a fresh Schedule singleton; push onto it.
    kernel.schedule.command("flag:cmd --force").everyMinute()

    result = await kernel.run_due_tasks(datetime.now(UTC))
    assert all(o.succeeded for o in result.outcomes)
    assert _FlagCmd.seen == [True]


async def test_scheduler_command_nonzero_marks_task_failed() -> None:
    kernel = _make_kernel_with_console(Application(commands=[_SyncFail()]))
    kernel.schedule.command("sync:fail").everyMinute()

    result = await kernel.run_due_tasks(datetime.now(UTC))
    assert any(o.failed for o in result.outcomes)
