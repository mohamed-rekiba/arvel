"""Arvel CLI — main Typer application.

Registers command groups for database operations, code generation, server,
materialized view management, queue workers, scheduler, routes, health, and publishing.
Auto-discovers application commands from ``app/Console/Commands/``.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import typer
import typer.core
import typer.main
import typer.models

if TYPE_CHECKING:
    from click import Command, Context

logger = logging.getLogger(__name__)

BANNER = r"""
    _                   _
   / \   _ ____   _____| |
  / _ \ | '__\ \ / / _ \ |
 / ___ \| |   \ V /  __/ |
/_/   \_\_|    \_/ \___|_|
"""

_LAZY_SUBCOMMANDS: dict[str, tuple[str, str, str]] = {
    "about": (
        "arvel.cli.commands.about", "about_app",
        "Show framework information.",
    ),
    "config": (
        "arvel.cli.commands.config_cmd", "config_app",
        "Configuration cache commands.",
    ),
    "db": (
        "arvel.cli.commands.db", "db_app",
        "Database migration and seeding commands.",
    ),
    "down": (
        "arvel.cli.commands.maintenance", "down",
        "Put the application into maintenance mode.",
    ),
    "health": (
        "arvel.cli.commands.health", "health_app",
        "Health check commands.",
    ),
    "make": (
        "arvel.cli.commands.make", "make_app",
        "Code generation commands.",
    ),
    "new": (
        "arvel.cli.commands.new", "new_project",
        "Create a new Arvel project.",
    ),
    "publish": (
        "arvel.cli.commands.publish", "publish_app",
        "Publish framework resources.",
    ),
    "queue": (
        "arvel.cli.commands.queue", "queue_app",
        "Queue worker management commands.",
    ),
    "route": (
        "arvel.cli.commands.route", "route_app",
        "Route inspection commands.",
    ),
    "schedule": (
        "arvel.cli.commands.schedule", "schedule_app",
        "Task scheduler management commands.",
    ),
    "serve": (
        "arvel.cli.commands.serve", "serve_app",
        "Start the development server.",
    ),
    "tinker": (
        "arvel.cli.commands.tinker", "tinker_app",
        "Interactive REPL with application context.",
    ),
    "up": (
        "arvel.cli.commands.maintenance", "up",
        "Bring the application out of maintenance mode.",
    ),
    "view": (
        "arvel.cli.commands.view", "view_app",
        "Materialized view management commands.",
    ),
}


class _LazyGroup(typer.core.TyperGroup):
    """Click group that defers subcommand imports until invocation.

    ``get_command`` returns lightweight stubs (for ``--help`` listing).
    ``resolve_command`` imports the real module when a subcommand is
    actually targeted by the user.
    """

    _lazy_subcommands: dict[str, tuple[str, str, str]]

    def list_commands(self, ctx: Context) -> list[str]:
        base = super().list_commands(ctx)
        lazy = sorted(self._lazy_subcommands.keys())
        return sorted(set(base + lazy))

    def get_command(self, ctx: Context, cmd_name: str) -> Command | None:
        if cmd_name not in self._lazy_subcommands:
            return super().get_command(ctx, cmd_name)
        _, _, help_text = self._lazy_subcommands[cmd_name]
        import click

        return click.Group(name=cmd_name, help=help_text)

    def resolve_command(
        self, ctx: Context, args: list[str],
    ) -> tuple[str | None, Command | None, list[str]]:
        cmd_name, cmd, remaining = super().resolve_command(ctx, args)
        if cmd_name and cmd_name in self._lazy_subcommands:
            real_cmd = self._import_real(cmd_name)
            if real_cmd is not None:
                cmd = real_cmd
        return cmd_name, cmd, remaining

    def _import_real(self, name: str) -> Command | None:
        module_path, attr_name, _ = self._lazy_subcommands[name]
        mod = importlib.import_module(module_path)
        attr = getattr(mod, attr_name, None)
        if attr is None:
            return None
        if isinstance(attr, typer.Typer):
            cmd = typer.main.get_group(attr)
            cmd.name = name
            return cmd
        if callable(attr):
            return typer.main.get_command_from_info(
                typer.models.CommandInfo(name=name, callback=attr),
                pretty_exceptions_short=True,
                rich_markup_mode=None,
            )
        return None


_LazyGroup._lazy_subcommands = _LAZY_SUBCOMMANDS

app = typer.Typer(
    name="arvel",
    help="Arvel framework CLI — migrations, seeders, generators, queue, scheduler.",
    no_args_is_help=True,
    cls=_LazyGroup,
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit."),
) -> None:
    """Arvel framework CLI."""
    if version:
        from importlib.metadata import version as pkg_version

        try:
            ver = pkg_version("arvel")
        except Exception:
            ver = "unknown"
        typer.echo(f"arvel {ver}")
        raise typer.Exit
    if ctx.invoked_subcommand is None:
        typer.echo(BANNER)
        ctx.get_help()
        raise typer.Exit


def discover_commands(base_path: Path | None = None) -> None:
    """Scan ``app/Console/Commands/*.py`` and register any Typer apps found.

    Each Python file that exports a ``typer.Typer`` instance is registered
    as a command group using the file's stem as the group name.
    """
    base = base_path or Path.cwd()
    commands_dir = base / "app" / "Console" / "Commands"
    if not commands_dir.is_dir():
        return

    for f in sorted(commands_dir.iterdir()):
        if not f.is_file() or f.suffix != ".py" or f.name.startswith("_"):
            continue

        module_name = f"app.Console.Commands.{f.stem}"
        spec = importlib.util.spec_from_file_location(module_name, str(f))
        if spec is None or spec.loader is None:
            continue

        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        try:
            spec.loader.exec_module(mod)
        except Exception:
            logger.warning("Failed to load command module %s: %s", f.name, sys.exc_info()[1])
            continue

        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            if isinstance(attr, typer.Typer):
                app.add_typer(attr, name=f.stem)
                break


discover_commands()
