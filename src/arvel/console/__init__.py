"""arvel.console — the CLI entry point (built on Typer + LazyGroup; DR-0002).

The root is a ``typer.Typer`` whose group class is :class:`~arvel.console.lazy.LazyGroup`,
so the dispatcher imports only the invoked command's module (T0 budget). ``main``
keeps the hottest paths (``--version``) on a stdlib fast-path that imports neither
typer nor rich. Heavy work (the full app boot for project commands) is deferred to
the command body. Grounded in knowledge/port/13-console.md.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from typing import TYPE_CHECKING, Any, NoReturn, TextIO

if TYPE_CHECKING:
    import contextlib
    import signal

    import typer

    from arvel.console.prompts import Prompter


class ConsoleOutput:
    """Command stdout/stderr I/O: ``info``/``line``/``comment``/
    ``question`` go to stdout, ``error``/``warn`` to stderr, ``table``/``with_progress_bar`` render
    to stdout. Built on click's ``echo``/``style``/``progressbar`` (typer's own backing library —
    ``arvel.console`` may not import ``rich`` directly; see import-linter's G2 contract) — no new
    dependency. ``out``/``err`` are injectable sinks (any writable text stream) so tests capture
    output without touching real stdio; left ``None`` they resolve to the live ``sys.stdout``/
    ``sys.stderr`` at print time (not at construction — so ``contextlib.redirect_stdout`` around an
    already-built ``ConsoleOutput`` still works, e.g. ``Cli.call_silently``)."""

    def __init__(self, out: TextIO | None = None, err: TextIO | None = None) -> None:
        self._out = out
        self._err = err

    def info(self, message: str) -> None:
        self._echo(message)

    def line(self, message: str = "") -> None:
        self._echo(message)

    def comment(self, message: str) -> None:
        self._echo(message)

    def question(self, message: str) -> None:
        self._echo(message)

    def error(self, message: str) -> None:
        self._echo(message, to_stderr=True, fg="red")

    def warn(self, message: str) -> None:
        self._echo(message, to_stderr=True, fg="yellow")

    def new_line(self, n: int = 1) -> None:
        for _ in range(n):
            self._echo("")

    def table(self, headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
        """A simple fixed-width table (no dependency beyond stdlib string formatting)."""
        columns = [str(h) for h in headers]
        data = [[str(cell) for cell in row] for row in rows]
        widths = [
            max(len(columns[i]), *(len(r[i]) for r in data)) if data else len(columns[i])
            for i in range(len(columns))
        ]

        def _row(cells: Sequence[str]) -> str:
            return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

        self._echo(_row(columns))
        self._echo("  ".join("-" * w for w in widths))
        for r in data:
            self._echo(_row(r))

    def with_progress_bar(self, iterable: Iterable[Any], *, label: str = "") -> Iterator[Any]:
        """Advance a progress bar over ``iterable`` — click's own
        ``progressbar`` context manager, rendered to this output's stdout sink."""
        import click

        with click.progressbar(iterable, label=label, file=self._out) as bar:
            yield from bar

    def _echo(self, message: str, *, to_stderr: bool = False, fg: str | None = None) -> None:
        import sys

        import click

        stream = (self._err if to_stderr else self._out) or (
            sys.stderr if to_stderr else sys.stdout
        )
        click.echo(click.style(message, fg=fg) if fg else message, file=stream)


class CommandFailed(Exception):
    """Raised by :meth:`Command.fail` — the kernel renders the message and exits 1."""


class Command:
    """Base class for app/ecosystem commands (Typer-wrapped at registration)."""

    signature: str = ""
    description: str = ""

    def __init__(
        self, output: ConsoleOutput | None = None, prompter: Prompter | None = None
    ) -> None:
        self.output = output or ConsoleOutput()
        if prompter is None:
            from arvel.console.prompts import Prompter as _Prompter

            prompter = _Prompter()
        self._prompter = prompter
        self._arguments: dict[str, Any] = {}
        self._options: dict[str, Any] = {}
        self._trap_scope: contextlib.ExitStack | None = None  # lazy — no-trap commands open none

    async def handle(self, *deps: Any) -> Any:  # DI-injected by the kernel
        raise NotImplementedError

    # -- output --------------------------------------------
    def info(self, message: str) -> None:
        self.output.info(message)

    def line(self, message: str = "") -> None:
        self.output.line(message)

    def comment(self, message: str) -> None:
        self.output.comment(message)

    def question(self, message: str) -> None:
        self.output.question(message)

    def error(self, message: str) -> None:
        self.output.error(message)

    def warn(self, message: str) -> None:
        self.output.warn(message)

    def new_line(self, n: int = 1) -> None:
        self.output.new_line(n)

    def table(self, headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
        self.output.table(headers, rows)

    def with_progress_bar(self, iterable: Iterable[Any], *, label: str = "") -> Iterator[Any]:
        return self.output.with_progress_bar(iterable, label=label)

    # -- prompts ------------------------------------------------
    def ask(self, label: str, default: str | None = None) -> str:
        return self._prompter.ask(label, default)

    def secret(self, label: str) -> str:
        return self._prompter.secret(label)

    def confirm(self, label: str, default: bool = False) -> bool:
        return self._prompter.confirm(label, default)

    def choice(self, label: str, options: Sequence[str], default: str | None = None) -> str:
        return self._prompter.choice(label, options, default)

    def anticipate(self, label: str, suggestions: Sequence[str], default: str | None = None) -> str:
        return self._prompter.anticipate(label, suggestions, default)

    # -- parsed CLI context (CLI-4: argument()/option() accessors) ----------------------
    def bind_parsed(self, values: dict[str, Any]) -> None:
        """Split ``values`` into arguments/options per this command's ``signature`` grammar (the
        kernel calls this right before ``handle`` — see ``console.kernel.run_command_class`` — so
        ``argument()``/``option()`` resolve). A required argument that wasn't supplied is asked
        for interactively (via the command's Prompter); without a TTY it fails with a usage error."""
        import sys

        from arvel.console.closure import parse_signature

        tokens = parse_signature(self.signature)
        self._arguments = {t.name: values.get(t.name) for t in tokens if not t.is_option}
        self._options = {t.name: values.get(t.name) for t in tokens if t.is_option}
        for token in tokens:
            if token.is_option or token.optional or self._arguments.get(token.name) is not None:
                continue
            if sys.stdin is not None and sys.stdin.isatty():
                self._arguments[token.name] = self.ask(f"{token.name}")
            else:
                self.fail(f"missing required argument: {token.name}")

    def fail(self, message: str) -> NoReturn:
        """Abort the command with ``message`` and exit code 1."""
        raise CommandFailed(message)

    # -- signal traps (E16) --------------------------------------------------
    def trap(self, sig: signal.Signals, handler: Callable[[], Any]) -> None:
        """Install ``handler`` for ``sig`` for the rest of this command's run — installs
        *immediately* (called from inside ``handle()``, where a running loop already exists on
        Unix), via the same shared mechanism ``queue:work``/``schedule:run`` use
        (:func:`arvel.support.signals.signal_traps`). Restored when this run's ``handle()``
        returns (the kernel closes the trap scope in ``finally`` — see
        ``console.kernel.run_command_class``)."""
        import contextlib

        from arvel.support.signals import signal_traps

        if self._trap_scope is None:
            self._trap_scope = contextlib.ExitStack()
        self._trap_scope.enter_context(signal_traps({sig: handler}))

    def _close_traps(self) -> None:
        """Restore every trap this run installed. A command that never called :meth:`trap` never
        opened a scope — a no-op, so its behavior is unchanged."""
        if self._trap_scope is not None:
            self._trap_scope.close()

    def argument(self, name: str) -> Any:
        return self._arguments.get(name)

    def option(self, name: str) -> Any:
        return self._options.get(name)


def build_cli() -> typer.Typer:
    """Construct the Typer application with the lazy command tree."""
    import typer

    from arvel.console.lazy import LazyGroup

    app = typer.Typer(cls=LazyGroup, add_completion=False, no_args_is_help=True)

    @app.callback()
    def _root() -> None:  # pyright: ignore[reportUnusedFunction]  # registered via decorator
        """arvel — a batteries-included async web framework for Python."""

    return app


def main() -> None:
    """Run the arvel CLI. ``--version`` and the bare banner are answered before
    importing Typer (T0 fast path — no typer/rich import)."""
    import sys

    argv = sys.argv[1:]
    if argv and argv[0] in ("--version", "-V"):
        from arvel import __version__

        print(__version__)
        return
    if not argv:
        from arvel import __version__
        from arvel.console.banner import print_banner

        print_banner(__version__)
        return
    build_cli()()


__all__ = [
    "Command",
    "CommandFailed",
    "ConsoleOutput",
    "build_cli",
    "main",
]
