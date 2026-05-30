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

1. ``asyncio.run(async_main())`` — one loop for the whole lifecycle.
2. ``framework_app.boot()`` — engine and all providers initialised on this loop.
3. Provider commands merged into the dispatch dict unconditionally.
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
import sys
from typing import TYPE_CHECKING

import typer

from arvel.console import Application, Command
from arvel.console._async import get_pending_task
from arvel.console._loader import discover_commands
from arvel.console.bootstrap import (
    bootstrap_framework_application,
    find_project_root,
)

if TYPE_CHECKING:
    from arvel.application import Application as FrameworkApplication

_log = logging.getLogger("arvel.console")

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


def _attach_provider_commands(
    framework_app: FrameworkApplication, commands_by_name: dict[str, Command]
) -> None:
    """Merge container-resolved commands into the dispatch dict (container wins).

    Provider commands are attached to the bound console Application by
    ``ConsoleServiceProvider.boot()``; we re-emit them here so the Typer app
    we build for ``main()`` actually sees them. On name collision the
    container-resolved binding replaces the entry-point one so user-provided
    providers can shadow built-ins.
    """
    try:
        console_app: Application = framework_app.container.make(Application)
    except Exception as exc:  # noqa: BLE001
        # Container resolution can raise for legitimate reasons (provider not
        # registered) — log and continue with entry-point commands only.
        _log.warning(
            "ConsoleServiceProvider not bound; provider commands unavailable (%s).",
            exc,
        )
        return

    for cmd in console_app.iter_commands():
        cmd.app = framework_app
        commands_by_name[cmd.name] = cmd


def _bind_app_to_needs_application_commands(
    framework_app: FrameworkApplication, commands_by_name: dict[str, Command]
) -> None:
    for cmd in commands_by_name.values():
        if cmd.needs_application:
            cmd.app = framework_app


async def async_main() -> None:
    """Run the full CLI lifecycle on a single event loop.

    Called by ``main()`` via ``asyncio.run()``; owns boot, dispatch, and shutdown.
    Typer reads from ``sys.argv``; no argument passing needed.
    """
    project_root = find_project_root()

    if project_root is None:
        # Allowed-outside-project path — no DI, no bootstrap, just entry-point commands.
        typer_app = build_app()
        typer_app()
        return

    # Inside a project: always boot so provider commands are available.
    discovered = discover_commands()
    commands_by_name: dict[str, Command] = {c.name: c for c in discovered}

    framework_app = bootstrap_framework_application(project_root)
    if framework_app is not None:
        await framework_app.boot()
        _attach_provider_commands(framework_app, commands_by_name)
        _bind_app_to_needs_application_commands(framework_app, commands_by_name)

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
        coro = get_pending_task()
        if coro is not None:
            await coro

        if _deferred_exit is not None:
            raise _deferred_exit
    finally:
        if framework_app is not None:
            await framework_app.shutdown()


def main() -> None:
    argv = sys.argv
    command = _requested_command(argv)
    project_root = find_project_root()

    if project_root is None and command is not None and not _is_outside_project_allowed(command):
        _print_outside_project_message(command)
        raise SystemExit(2)

    if project_root is None:
        # Allowed-outside-project path — sync fast-path, no loop needed.
        typer_app = build_app()
        typer_app()
        raise SystemExit(0)

    asyncio.run(async_main())
