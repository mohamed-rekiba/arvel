"""Arvel console layer — Application, Command, Context."""

from __future__ import annotations

import contextlib
import io
import logging
from abc import abstractmethod
from typing import TYPE_CHECKING, ClassVar

import typer

from arvel.console._subsystem import CliSubsystem

if TYPE_CHECKING:
    from arvel.application import Application as FrameworkApplication

_log = logging.getLogger("arvel.console")


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

    def call(self, name: str, args: list[str] | None = None) -> int:
        """Invoke another registered command in-process and return its exit code.

        Requires a bound framework Application (``self.app``) — typically set
        by the entrypoint when ``requires`` is non-empty. Use ``call_silently``
        to suppress stdout from the invoked command.
        """
        return self._invoke_via_console(name, args, silent=False)

    def call_silently(self, name: str, args: list[str] | None = None) -> int:
        """Same as :meth:`call`, but stdout from the invoked command is discarded."""
        return self._invoke_via_console(name, args, silent=True)

    def _invoke_via_console(self, name: str, args: list[str] | None, *, silent: bool) -> int:
        if self.app is None:
            msg = (
                f"Command.call({name!r}) requires a bound framework Application; "
                f"add the subsystems you need to {type(self).__name__}.requires."
            )
            raise RuntimeError(msg)
        console_app: Application = self.app.container.make(Application)
        if silent:
            with contextlib.redirect_stdout(io.StringIO()):
                return console_app.run(name, args)
        return console_app.run(name, args)


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

    def run(self, name: str, args: list[str] | None = None) -> int:
        """Invoke a registered command by name and return its exit code.

        Bypasses Typer's CLI parsing — this is the in-process programmatic
        entry-point used by the scheduler kernel's ``run_command`` hook. The
        ``args`` parameter is accepted for forward compatibility but is not
        currently passed through, because the wired use case (scheduled
        commands by name) has no positional/keyword arguments.

        Raises ``KeyError`` when ``name`` does not match any registered
        command.
        """
        _ = args  # reserved for future argv passthrough
        try:
            command = self._commands[name]
        except KeyError as exc:
            msg = f"Unknown command: {name!r}"
            raise KeyError(msg) from exc
        ctx = Context()
        return command.handle(ctx)
