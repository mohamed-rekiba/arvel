"""WI-014 — async CLI commands honor the single-loop contract.

The entrypoint owns the one event loop (``asyncio.run(async_main())``) and
dispatches Typer synchronously on it. A command callback that calls
``asyncio.run()`` therefore nests on the live loop and crashes in-project with
"asyncio.run() cannot be called from a running event loop". WI-031 fixed this
for migrate/db:seed via ``schedule_async``; this WI brings the rest of the
async commands onto the same contract and makes the entrypoint translate a
deferred coroutine's ``typer.Exit``/``Abort`` into the process exit code.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import typer
from arvel.console._async import clear_pending_task, get_pending_task, schedule_async
from arvel.console._subsystem import CliSubsystem


@pytest.fixture(autouse=True)
def clean_async_slot() -> Iterator[None]:
    clear_pending_task()
    yield
    coro = get_pending_task()
    if coro is not None and asyncio.iscoroutine(coro):
        coro.close()
    clear_pending_task()


def _invoke_first_callback(cmd: Any, **kwargs: Any) -> None:
    typer_app = typer.Typer()
    cmd.register(typer_app)
    for registered in typer_app.registered_commands:
        if registered.callback is not None:
            with contextlib.suppress(Exception):
                registered.callback(**kwargs)
            return


def _async_command_cases() -> list[tuple[type[Any], dict[str, Any]]]:
    from arvel.console.commands.auth_clear_resets import AuthClearResetsCommand
    from arvel.console.commands.cache_commands import CacheClearCommand, CacheForgetCommand
    from arvel.console.commands.db_show import DbShowCommand
    from arvel.console.commands.db_table import DbTableCommand
    from arvel.console.commands.queue_clear import QueueClearCommand
    from arvel.console.commands.queue_prune_failed import QueuePruneFailedCommand
    from arvel.console.commands.queue_restart import QueueRestartCommand
    from arvel.console.commands.schedule_run import ScheduleRunCommand

    return [
        (CacheClearCommand, {}),
        (CacheForgetCommand, {"key": "k"}),
        (DbShowCommand, {}),
        (DbTableCommand, {"table": "users"}),
        (QueueClearCommand, {}),
        (QueuePruneFailedCommand, {}),
        (QueueRestartCommand, {}),
        (AuthClearResetsCommand, {}),
        (ScheduleRunCommand, {}),
    ]


@pytest.mark.parametrize(("cmd_cls", "kwargs"), _async_command_cases())
def test_callback_defers_via_schedule_async_not_asyncio_run(
    cmd_cls: type[Any], kwargs: dict[str, Any]
) -> None:
    """No async command may call asyncio.run() in its Typer callback."""
    cmd = cmd_cls()
    cmd.app = MagicMock()
    with (
        patch("asyncio.run") as mock_run,
        patch("arvel.console._async.schedule_async", wraps=schedule_async) as mock_sched,
    ):
        _invoke_first_callback(cmd, **kwargs)

    mock_run.assert_not_called()
    mock_sched.assert_called_once()


def test_cache_commands_require_cache_subsystem() -> None:
    """cache:clear / cache:forget must boot the cache provider, not foundation-only."""
    from arvel.console.commands.cache_commands import CacheClearCommand, CacheForgetCommand

    assert CliSubsystem.CACHE in CacheClearCommand.requires
    assert CliSubsystem.CACHE in CacheForgetCommand.requires


def test_queue_restart_requires_cache_subsystem() -> None:
    """queue:restart writes the restart marker via the cache facade."""
    from arvel.console.commands.queue_restart import QueueRestartCommand

    assert CliSubsystem.CACHE in QueueRestartCommand.requires


# ─── entrypoint: deferred coro's typer.Exit becomes the process exit code ─────


def _make_failing_command(exit_code: int) -> Any:
    from arvel.console import Command, Context

    class _Failing(Command):
        name = "wi014:fail"
        help = "deferred failure"

        def register(self, app: typer.Typer) -> None:
            def _cb() -> None:
                async def _run() -> None:
                    raise typer.Exit(code=exit_code)

                schedule_async(_run())

            app.command(name=self.name, help=self.help)(_cb)

        def handle(self, ctx: Context) -> int:
            raise NotImplementedError

    return _Failing()


def _patch_entrypoint(monkeypatch: pytest.MonkeyPatch, ep: Any, cmd: Any) -> None:
    def _no_bootstrap(*_a: object, **_k: object) -> None:
        return None

    def _no_subsystems(_command: object) -> frozenset[CliSubsystem]:
        return frozenset()

    def _only_cmd(*_a: object, **_k: object) -> dict[str, Any]:
        return {cmd.name: cmd}

    monkeypatch.setattr(ep, "bootstrap_framework_application", _no_bootstrap)
    monkeypatch.setattr(ep, "_required_subsystems_for", _no_subsystems)
    monkeypatch.setattr(ep, "_select_in_project_commands", _only_cmd)
    monkeypatch.setattr(sys, "argv", ["arvel", cmd.name])


def test_async_main_translates_deferred_typer_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """A typer.Exit raised inside the deferred coroutine sets the process code."""
    import arvel.console.entrypoint as ep

    cmd = _make_failing_command(7)
    _patch_entrypoint(monkeypatch, ep, cmd)

    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(ep.async_main(tmp_path, cmd.name))
    assert exc_info.value.code == 7


def test_async_main_exit_zero_on_deferred_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """A deferred coroutine that returns normally exits 0, not a traceback."""
    import arvel.console.entrypoint as ep
    from arvel.console import Command, Context

    ran: list[bool] = []

    class _Ok(Command):
        name = "wi014:ok"
        help = "deferred success"

        def register(self, app: typer.Typer) -> None:
            def _cb() -> None:
                async def _run() -> None:
                    ran.append(True)

                schedule_async(_run())

            app.command(name=self.name, help=self.help)(_cb)

        def handle(self, ctx: Context) -> int:
            raise NotImplementedError

    cmd = _Ok()
    _patch_entrypoint(monkeypatch, ep, cmd)

    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(ep.async_main(tmp_path, cmd.name))
    assert exc_info.value.code == 0
    assert ran == [True]
