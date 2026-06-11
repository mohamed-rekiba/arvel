"""Arvel console layer — Application, Command, Context."""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
from abc import abstractmethod
from typing import TYPE_CHECKING, ClassVar

import click
import typer
from typer.main import get_command

from arvel.console._async import clear_pending_task, get_pending_task
from arvel.console._async import schedule_async as schedule_async
from arvel.console._subsystem import CliSubsystem

if TYPE_CHECKING:
    from collections.abc import Sequence

    from arvel.application import Application as FrameworkApplication

_log = logging.getLogger("arvel.console")


def _coerce_exit_code(code: int | str | None) -> int:
    """Map a SystemExit code (int | str | None) to a process exit code."""
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    return 1


class Context:
    """I/O surface passed to ``Command.handle()``.

    Method names mirror Laravel Artisan's command I/O so it's familiar to
    anyone coming from PHP. Output goes to stdout for status/info
    channels and stderr for ``error()`` — the latter mirrors the convention
    that exit codes are paired with stderr messages.
    """

    def info(self, message: str) -> None:
        """Write an informational line to stdout."""
        typer.echo(message)

    def error(self, message: str) -> None:
        """Write a failure line to stderr (pair with a non-zero exit code)."""
        typer.echo(message, err=True)

    def line(self, message: str = "") -> None:
        """Write a plain line (no styling) to stdout."""
        typer.echo(message)

    def warn(self, message: str) -> None:
        """Write a warning line to stdout (caller decides on exit code)."""
        typer.echo(message)

    def comment(self, message: str) -> None:
        """Write a comment/annotation line to stdout (Artisan parity)."""
        typer.echo(message)

    def alert(self, message: str) -> None:
        """Write a high-visibility alert to stdout (Artisan parity)."""
        typer.echo(message)

    def newline(self, count: int = 1) -> None:
        """Emit ``count`` blank lines to stdout. Defaults to one."""
        for _ in range(count):
            typer.echo("")


class Command:
    """Abstract base for all Arvel console commands.

    Simple commands override ``handle(ctx)``.
    Commands with typed CLI arguments override ``register(app)`` instead.

    Subclasses opt into framework DI by listing the subsystems they need on
    :attr:`requires`. The CLI entrypoint computes the transitive closure of
    those subsystems and boots only the matching providers, then binds the
    resulting :class:`arvel.application.Application` to ``self.app``. Commands
    with an empty ``requires`` and ``requires_project_context = False`` skip
    framework bootstrap entirely (``self.app is None``) — that's the fast
    path for pure generators like ``make:controller`` and ``new``.
    """

    name: ClassVar[str]
    help: ClassVar[str] = ""

    #: Subsystems this command needs. The entrypoint computes ``closure(requires)
    #: | FOUNDATION_SUBSYSTEMS`` and boots exactly those providers. Empty =
    #: foundation-only (no provider boot at all when ``requires_project_context``
    #: is also False).
    requires: ClassVar[frozenset[CliSubsystem]] = frozenset()

    #: Set True for commands that need ``Application.base_path`` and the project
    #: layout but no provider boot — e.g. ``serve`` (uvicorn re-imports the ASGI
    #: app and boots it via lifespan, so we just need to know where the project
    #: lives).
    requires_project_context: ClassVar[bool] = False

    #: The command takes over the process and manages its own event loop
    #: (e.g. ``serve`` → uvicorn, which calls ``asyncio.run`` internally). The
    #: entrypoint dispatches such commands *outside* its ``asyncio.run`` wrapper,
    #: otherwise uvicorn raises "asyncio.run() cannot be called from a running
    #: event loop".
    owns_process: ClassVar[bool] = False

    #: Bound by the entrypoint when ``requires`` is non-empty (or
    #: ``requires_project_context`` is True) AND a project root is
    #: discoverable. ``None`` otherwise.
    app: FrameworkApplication | None = None

    @classmethod
    def needs_framework(cls) -> bool:
        """Derived signal: does this command trigger a framework bootstrap?"""
        return bool(cls.requires) or cls.requires_project_context

    def register(self, app: typer.Typer) -> None:
        """Register this command with the Typer app. Default: no-arg callback."""
        cmd_self = self

        def _callback() -> None:
            ctx = Context()
            code = cmd_self.handle(ctx)
            if code != 0:
                raise typer.Exit(code)

        app.command(name=self.name, help=self.help)(_callback)

    @abstractmethod
    def handle(self, ctx: Context) -> int:
        """Execute the command. Return 0 for success, non-zero for failure."""

    async def call(self, name: str, *args: str) -> int:
        """Invoke another registered command in-process and return its exit code.

        Dispatches through the target's real Typer callback, so ``args`` are
        parsed as CLI flags and an async command's deferred coroutine is awaited
        — same path the entrypoint uses. Requires a bound framework Application
        (``self.app``). Await it from a coroutine (composite commands defer their
        body via ``schedule_async``). Use ``call_silently`` to swallow the
        invoked command's stdout.
        """
        return await self._invoke_via_console(name, args, silent=False)

    async def call_silently(self, name: str, *args: str) -> int:
        """Same as :meth:`call`, but stdout from the invoked command is discarded."""
        return await self._invoke_via_console(name, args, silent=True)

    async def _invoke_via_console(self, name: str, args: Sequence[str], *, silent: bool) -> int:
        if self.app is None:
            msg = (
                f"Command.call({name!r}) requires a bound framework Application; "
                f"add the subsystems you need to {type(self).__name__}.requires."
            )
            raise RuntimeError(msg)
        console_app: Application = self.app.container.make(Application)
        if silent:
            # Redirect spans the await: _run_click runs the callback synchronously
            # and the deferred coroutine writes here too. Fine for sequential CLI
            # dispatch; a sibling coroutine running concurrently would also be caught.
            with contextlib.redirect_stdout(io.StringIO()):
                return await console_app.adispatch(name, args)
        return await console_app.adispatch(name, args)


class Application:
    """Arvel CLI application — wraps Typer and manages command registration."""

    def __init__(self, commands: list[Command]) -> None:
        self.typer_app = typer.Typer(add_completion=False)

        # Prevent Typer from "promoting" a single subcommand to the root command.
        def _noop(ctx: typer.Context) -> None:
            if ctx.invoked_subcommand is None:
                typer.echo(ctx.get_help())

        self.typer_app.callback(invoke_without_command=True)(_noop)

        self._commands: dict[str, Command] = {}

        # Collect commands — last registration wins on collision (log a warning)
        for cmd in commands:
            if cmd.name in self._commands:
                _log.warning(
                    "Command %r registered more than once; last registration wins.", cmd.name
                )
            self._commands[cmd.name] = cmd

        # Register deduplicated commands with Typer
        for cmd in self._commands.values():
            cmd.register(self.typer_app)

    def iter_commands(self) -> list[Command]:
        """Snapshot of the currently-registered commands.

        Returned as a list so callers can iterate while the underlying
        registry is mutated (e.g., by ``ConsoleServiceProvider.boot()``).
        """
        return list(self._commands.values())

    def has_command(self, name: str) -> bool:
        """Return True if a command with ``name`` is registered."""
        return name in self._commands

    def register_command(self, cmd: Command) -> None:
        """Register a Command after construction.

        Used by ``ConsoleServiceProvider.boot`` to attach provider-owned
        commands once their dependencies have been wired. Re-registering a
        name overwrites the previous binding and logs a warning so the
        collision is auditable.
        """
        if cmd.name in self._commands:
            _log.warning("Command %r registered more than once; last registration wins.", cmd.name)
        self._commands[cmd.name] = cmd
        cmd.register(self.typer_app)

    async def adispatch(self, name: str, args: Sequence[str] = ()) -> int:
        """Run a registered command through Typer with ``args``; return its exit code.

        The single programmatic dispatch core — used by :meth:`run`, the
        scheduler's ``run_command`` hook, and :meth:`Command.call`. It drives the
        command's real ``register()``-installed Typer callback (so ``args`` parse
        as flags) and then awaits the coroutine that callback deferred via
        ``schedule_async`` — the same two-step the entrypoint runs after Typer
        returns. That's why scheduling or calling an async command (``migrate``,
        ``queue:*``) finally works: their real work lives in the deferred
        coroutine, not in ``handle()``.

        Runs on the caller's event loop. Raises ``KeyError`` for an unknown name
        (kept separate from Typer's "no such command" so callers can distinguish
        a typo from a usage error).
        """
        if name not in self._commands:
            msg = f"Unknown command: {name!r}"
            raise KeyError(msg)
        # Isolate this invocation's deferral slot from any caller (e.g. a
        # composite command whose own coroutine is mid-flight).
        clear_pending_task()
        try:
            code = self._invoke_click([name, *args])
            coro = get_pending_task()
            if coro is not None:
                try:
                    await coro
                except typer.Exit as exc:
                    code = exc.exit_code
                except typer.Abort:
                    code = 1
        finally:
            clear_pending_task()
        return code

    def _invoke_click(self, argv: list[str]) -> int:
        """Invoke the Typer/Click command non-standalone and normalise the exit code.

        ``standalone_mode=False`` keeps Click from calling ``sys.exit`` — a
        ``typer.Exit`` from a synchronous (``handle``-based) command comes back
        as the return value on some Click versions and as a raised ``Exit`` on
        others, so handle both. Usage errors are shown and mapped to their code.
        """
        command = get_command(self.typer_app)
        try:
            result = command(args=argv, standalone_mode=False)
        except typer.Exit as exc:
            return exc.exit_code
        except click.exceptions.Abort:
            return 1
        except click.ClickException as exc:
            exc.show()
            return exc.exit_code
        except SystemExit as exc:
            return _coerce_exit_code(exc.code)
        return result if isinstance(result, int) else 0

    def run(self, name: str, args: Sequence[str] = ()) -> int:
        """Synchronous wrapper over :meth:`adispatch` for callers without a loop.

        Spins a fresh event loop via ``asyncio.run``, so it must NOT be called
        from inside a running loop — use ``await adispatch(...)`` there. Raises
        ``KeyError`` when ``name`` is unknown.
        """
        return asyncio.run(self.adispatch(name, args))
