"""Arvel framework CLI entrypoint — discovers commands, boots the framework, runs Typer.

Built-in commands are declared under ``[project.entry-points."arvel.commands"]``
in ``packages/arvel/pyproject.toml``. Optional commands gated by extras (e.g.
``reverb:start`` when ``[broadcasting]`` is installed) plug in automatically;
when their extra is missing, ``discover_commands()`` skips them with a warning.

The entrypoint owns the single ``asyncio`` event loop for the entire CLI
invocation. Commands that need to run async work call :func:`schedule_async`
from ``arvel.console._async``; the deferred coroutine is awaited here after
Typer dispatch returns.

Sequence inside a project:

1. ``asyncio.run(async_main(project_root, command))`` — one loop for the whole lifecycle.
2. ``framework_app.boot()`` — engine and all providers initialised on this loop.
3. Provider commands collected from the container; for a concrete ``command`` only
   that one command is loaded (no full discovery — keeps startup off the heavy stack).
4. Typer parses and dispatches; async commands call ``schedule_async(coro)``.
5. Scheduled coroutine awaited on the live loop.
6. ``framework_app.shutdown()`` in ``finally`` — engine disposed on the same loop.

When invoked outside an Arvel project, the entrypoint allows safe commands
(``--help``, ``--version``, ``about``, ``make:*``, ``key:generate``, ``new``)
and otherwise prints a hint pointing at ``arvel new``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import TYPE_CHECKING

import typer

from arvel import __version__
from arvel.console import Application, Command
from arvel.console._async import get_pending_task
from arvel.console._command_meta import COMMAND_HELP
from arvel.console._loader import discover_commands, entry_point_names, load_command
from arvel.console._subsystem import CliSubsystem, closure
from arvel.console._venv import maybe_reexec_into_project_venv
from arvel.console.bootstrap import (
    bootstrap_framework_application,
    find_project_root,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from arvel.application import Application as FrameworkApplication

_log = logging.getLogger("arvel.console")

_BANNER = r"""
   __ _  _ ____   __  ___  __
  / _` || '__\ \ / / / _ \| |
 | (_| || |   \ V / |  __/| |
  \__,_||_|    \_/   \___||_|
"""

_ANSI_CYAN = "\033[1;36m"
_ANSI_DIM = "\033[2m"
_ANSI_RESET = "\033[0m"

# Commands that must work outside a project (no bootstrap/app.py required).
_OUTSIDE_PROJECT_ALLOWED_PREFIXES: tuple[str, ...] = ("make:",)
_OUTSIDE_PROJECT_ALLOWED_NAMES: frozenset[str] = frozenset({"about", "key:generate", "new"})
_OUTSIDE_PROJECT_ALLOWED_FLAGS: frozenset[str] = frozenset({"--help", "-h", "--version", "-V"})


def get_commands() -> list[Command]:
    """Collect every CLI command from the ``arvel.commands`` entry-point group."""
    return discover_commands()


def build_app() -> typer.Typer:
    """Build and return the Typer application (for testing)."""
    app = Application(get_commands())
    return app.typer_app


def _requested_command(argv: list[str]) -> str | None:
    """Return the first positional argument from ``argv`` (the command name) or None."""
    for token in argv[1:]:
        if token.startswith("-"):
            continue
        return token
    return None


def _banner_suppressed(argv: list[str]) -> bool:
    return (
        "--no-banner" in argv or bool(os.environ.get("ARVEL_NO_BANNER")) or not sys.stderr.isatty()
    )


def _print_banner(argv: list[str]) -> None:
    """Print the arvel banner to stderr before anything else.

    On stderr so it never corrupts stdout (``openapi:export``, ``route:list``
    piped to grep, JSON output...). TTY-gated and opt-out via ``--no-banner`` /
    ``ARVEL_NO_BANNER`` so scripts and CI stay clean. ``NO_COLOR`` drops the
    ANSI styling but still shows the banner.
    """
    if _banner_suppressed(argv):
        return
    if os.environ.get("NO_COLOR"):
        typer.echo(_BANNER, err=True)
        typer.echo(f"  arvel {__version__} — the Laravel of Python\n", err=True)
        return
    typer.echo(f"{_ANSI_CYAN}{_BANNER}{_ANSI_RESET}", err=True)
    typer.echo(
        f"  {_ANSI_DIM}arvel {__version__} — the Laravel of Python{_ANSI_RESET}\n",
        err=True,
    )


def build_listing_app() -> typer.Typer:
    """Typer app that lists every command for ``arvel --help`` without importing one.

    Rendering the top-level listing only needs each command's name + short help.
    Importing the ~70 command classes to get that drags in FastAPI, SQLAlchemy,
    Starlette, and Jinja2 (~3.9s cold). Instead we register render-only placeholders
    from the generated ``COMMAND_HELP`` manifest. Real dispatch (``arvel <cmd>`` and
    ``arvel <cmd> --help``) never lands here — it routes through :func:`load_command`
    first — so the placeholder callbacks are only hit for an entry point that exists
    but fails to import, where a clear error beats a silent no-op.
    """
    app = typer.Typer(add_completion=False)

    def _noop(ctx: typer.Context) -> None:
        if ctx.invoked_subcommand is None:
            typer.echo(ctx.get_help())

    app.callback(invoke_without_command=True)(_noop)

    def _make_unavailable(cmd_name: str) -> Callable[[], None]:
        def _cb() -> None:
            typer.echo(f"Command {cmd_name!r} is unavailable (failed to load).", err=True)
            raise typer.Exit(1)

        return _cb

    for name in entry_point_names():
        app.command(name=name, help=COMMAND_HELP.get(name, ""))(_make_unavailable(name))

    return app


def _resolve_typer(command: str | None) -> typer.Typer:
    """Build the Typer app, loading only ``command`` when it's a concrete name.

    The hot path — running one command outside a project — shouldn't import all
    ~70 command modules. Falls back to the manifest-backed listing app for
    ``--help``/no-arg (which must list every command) and for an unknown name (so
    Typer renders a proper "no such command"), neither of which imports a command.
    """
    if command is not None:
        only = load_command(command)
        if only is not None:
            return Application([only]).typer_app
    return build_listing_app()


def _is_outside_project_allowed(command: str | None) -> bool:
    if command is None:
        return True
    if command in _OUTSIDE_PROJECT_ALLOWED_FLAGS:
        return True
    if command in _OUTSIDE_PROJECT_ALLOWED_NAMES:
        return True
    return any(command.startswith(prefix) for prefix in _OUTSIDE_PROJECT_ALLOWED_PREFIXES)


def _print_outside_project_message(command: str | None) -> None:
    typer.echo(
        "ERROR: No Arvel project found in the current directory or its ancestors.\n"
        "\n"
        f"The command '{command or ''}' needs a project context (bootstrap/app.py).\n"
        "\n"
        "If you want to create a new Arvel project, run:\n"
        "\n"
        "    arvel new my-app\n"
        "    cd my-app\n"
        "\n"
        "Then re-run your command from inside the project.",
        err=True,
    )


def _provider_commands(framework_app: FrameworkApplication) -> dict[str, Command]:
    """Commands registered by providers during boot, keyed by name (``app`` bound).

    Provider commands are attached to the bound console Application by
    ``ConsoleServiceProvider.boot()``. Returns ``{}`` when the console
    Application isn't bound (provider not registered) so the CLI still works
    with entry-point commands only.
    """
    try:
        console_app: Application = framework_app.container.make(Application)
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "ConsoleServiceProvider not bound; provider commands unavailable (%s).",
            exc,
        )
        return {}

    out: dict[str, Command] = {}
    for cmd in console_app.iter_commands():
        cmd.app = framework_app
        out[cmd.name] = cmd
    return out


def _bind_framework_to_commands(
    framework_app: FrameworkApplication, commands_by_name: dict[str, Command]
) -> None:
    for cmd in commands_by_name.values():
        if cmd.needs_framework():
            cmd.app = framework_app


def _select_in_project_commands(
    command: str | None,
    framework_app: FrameworkApplication | None,
    provider_cmds: dict[str, Command],
) -> dict[str, Command]:
    """Pick the commands to register for in-project dispatch.

    For a concrete command we load just that one (provider binding wins over the
    entry-point class) so a single ``arvel migrate`` doesn't import all ~70
    command modules — which would drag in SQLAlchemy/FastAPI/Jinja2/uvicorn. Only
    ``arvel`` / ``--help`` / an unknown name fall back to full discovery, where
    Typer needs every command to render the listing (or a proper "no such
    command").
    """
    if command is not None:
        cmd = provider_cmds.get(command)
        if cmd is None:
            cmd = load_command(command)
            if cmd is not None and framework_app is not None and cmd.needs_framework():
                cmd.app = framework_app
        if cmd is not None:
            return {cmd.name: cmd}

    commands_by_name: dict[str, Command] = {c.name: c for c in discover_commands()}
    commands_by_name.update(provider_cmds)  # provider binding wins on name collision
    if framework_app is not None:
        _bind_framework_to_commands(framework_app, commands_by_name)
    return commands_by_name


def _required_subsystems_for(command: str | None) -> frozenset[CliSubsystem] | None:
    """Compute the subsystem closure for ``command`` without instantiating it.

    Returns ``None`` when ``command`` is unknown or has no resolvable class —
    the caller treats that as "boot the full chain" so help/listing paths keep
    working. Returns the empty frozenset for commands declaring no subsystems
    (foundation-only providers will still load).
    """
    if command is None:
        return None
    cmd = load_command(command)
    if cmd is None:
        return None
    cls = type(cmd)
    if not cls.needs_framework():
        return frozenset()
    return closure(cls.requires)


async def async_main(project_root: Path, command: str | None) -> None:
    """Run the in-project CLI lifecycle on a single event loop.

    Only reached from ``main()`` when a project root exists — ``main()`` handles
    the outside-project fast path itself. Owns boot, dispatch, and shutdown.
    Typer reads from ``sys.argv``; ``command`` is the resolved name (or None) used
    to load only what dispatch needs.
    """
    required = _required_subsystems_for(command)
    framework_app = bootstrap_framework_application(project_root, required_subsystems=required)
    provider_cmds: dict[str, Command] = {}
    if framework_app is not None:
        await framework_app.boot()
        provider_cmds = _provider_commands(framework_app)

    commands_by_name = _select_in_project_commands(command, framework_app, provider_cmds)

    # Typer/Click raises SystemExit(0) after a successful command in standalone
    # mode. We must catch it so get_pending_task() can still run — otherwise
    # schedule_async() coroutines (scheduler loop, migrations, etc.) are
    # GC'd without ever being awaited.
    _deferred_exit: SystemExit | None = None
    try:
        app = Application(list(commands_by_name.values()))
        try:
            app.typer_app()
        except SystemExit as exc:
            _deferred_exit = exc

        # Await any coroutine that a command deferred via schedule_async().
        # Typer's main() has already returned, so a typer.Exit/Abort raised
        # inside the deferred coroutine won't be turned into a process exit
        # code — translate it here. Otherwise the command's honest failure code
        # escapes as an uncaught RuntimeError (traceback + exit 1).
        coro = get_pending_task()
        if coro is not None:
            try:
                await coro
            except typer.Exit as exc:
                raise SystemExit(exc.exit_code) from exc
            except typer.Abort as exc:
                raise SystemExit(1) from exc

        if _deferred_exit is not None:
            raise _deferred_exit
    finally:
        if framework_app is not None:
            await framework_app.shutdown()


def main() -> None:
    argv = sys.argv

    # Hand off to the project's .venv interpreter before anything else (incl. the
    # banner) so the whole run uses the project-pinned arvel + its deps. Never
    # returns when a re-exec happens; otherwise we're already on the right one.
    maybe_reexec_into_project_venv(argv)

    _print_banner(argv)

    # `--no-banner` is ours, not Typer's — strip it so dispatch doesn't choke.
    if "--no-banner" in argv:
        argv[:] = [arg for arg in argv if arg != "--no-banner"]

    if any(flag in argv for flag in ("--version", "-V")):
        typer.echo(f"arvel {__version__}")
        raise SystemExit(0)

    command = _requested_command(argv)
    project_root = find_project_root()

    if project_root is None and command is not None and not _is_outside_project_allowed(command):
        _print_outside_project_message(command)
        raise SystemExit(2)

    if project_root is None:
        # Allowed-outside-project path — sync fast-path, no loop needed.
        _resolve_typer(command)()
        raise SystemExit(0)

    # Commands that own the process (e.g. `serve` → uvicorn) must run outside
    # the asyncio.run wrapper below — uvicorn calls asyncio.run() itself and
    # would otherwise hit "cannot be called from a running event loop". They
    # don't need the framework booted in the CLI process; uvicorn re-imports
    # the ASGI app and boots it via lifespan. Load only the requested command.
    if command is not None:
        owning = load_command(command)
        if owning is not None and owning.owns_process:
            Application([owning]).typer_app()
            raise SystemExit(0)

    try:
        asyncio.run(async_main(project_root, command))
    except KeyboardInterrupt:
        # Ctrl+C during a long-running command (e.g. schedule:work). The command
        # already logged its graceful-shutdown message and shutdown() ran in the
        # finally block; exit with the conventional SIGINT code, no traceback.
        raise SystemExit(130) from None
