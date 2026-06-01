"""Queue commands test helpers."""

from __future__ import annotations

import asyncio
import io
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from typing import Any

import click
from typer.testing import CliRunner


@dataclass
class InvokeResult:
    """Combined result from a sync Typer dispatch + deferred async coroutine."""

    exit_code: int
    output: str = field(default="")

    @property
    def stdout(self) -> str:
        return self.output

    @property
    def stderr(self) -> str:
        # CliRunner defaults to mix_stderr=True; match that convention.
        return self.output

    @property
    def exception(self) -> BaseException | None:
        return None


def invoke_async(
    runner: CliRunner,
    typer_app: Any,
    args: list[str] | None = None,
    **kwargs: Any,
) -> InvokeResult:
    """Invoke *typer_app* via CliRunner and run any work deferred by schedule_async.

    Commands that use ``schedule_async`` defer their coroutine to the
    entrypoint's event loop. In unit tests that bypass the entrypoint, nothing
    awaits the coroutine. This helper bridges the gap: runs the sync dispatch
    first, then runs the scheduled coroutine (if any) and captures its output.
    """
    from arvel.console._async import clear_pending_task, get_pending_task

    clear_pending_task()

    sync_result = runner.invoke(typer_app, args or [], **kwargs)

    coro = get_pending_task()
    clear_pending_task()

    if coro is None:
        return InvokeResult(
            exit_code=sync_result.exit_code,
            output=sync_result.output,
        )

    async_buf = io.StringIO()
    async_exit_code: int | None = None

    with redirect_stdout(async_buf), redirect_stderr(async_buf):
        try:
            asyncio.run(coro)
        except click.exceptions.Exit as exc:
            async_exit_code = exc.exit_code
        except click.exceptions.Abort:
            async_exit_code = 1
        except SystemExit as exc:
            code = exc.code
            async_exit_code = code if isinstance(code, int) else 1
        except BaseException:
            # Matches CliRunner's default catch_exceptions=True behaviour.
            async_exit_code = 1

    combined_output = sync_result.output + async_buf.getvalue()
    final_exit_code = async_exit_code if async_exit_code is not None else sync_result.exit_code

    return InvokeResult(exit_code=final_exit_code, output=combined_output)


__all__ = ["InvokeResult", "invoke_async"]
