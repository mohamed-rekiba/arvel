"""Arvel CLI — main Typer application.

Registers command groups for database operations, code generation, server,
materialized view management, queue workers, scheduler, routes, health, and publishing.
Auto-discovers application commands from ``app/Console/Commands/``.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

import typer

from arvel.cli.commands.about import about_app
from arvel.cli.commands.config_cmd import config_app
from arvel.cli.commands.db import db_app
from arvel.cli.commands.health import health_app
from arvel.cli.commands.maintenance import down, up
from arvel.cli.commands.make import make_app
from arvel.cli.commands.new import new_project
from arvel.cli.commands.publish import publish_app
from arvel.cli.commands.queue import queue_app
from arvel.cli.commands.route import route_app
from arvel.cli.commands.schedule import schedule_app
from arvel.cli.commands.serve import serve_app
from arvel.cli.commands.tinker import tinker_app
from arvel.cli.commands.view import view_app

logger = logging.getLogger(__name__)

BANNER = r"""
    _                   _
   / \   _ ____   _____| |
  / _ \ | '__\ \ / / _ \ |
 / ___ \| |   \ V /  __/ |
/_/   \_\_|    \_/ \___|_|
"""


app = typer.Typer(
    name="arvel",
    help="Arvel framework CLI — migrations, seeders, generators, queue, scheduler.",
    no_args_is_help=True,
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


app.add_typer(db_app, name="db")
app.add_typer(make_app, name="make")
app.add_typer(view_app, name="view")
app.add_typer(queue_app, name="queue")
app.add_typer(schedule_app, name="schedule")
app.add_typer(route_app, name="route")
app.add_typer(health_app, name="health")
app.add_typer(serve_app, name="serve")
app.add_typer(about_app, name="about")
app.command(name="new")(new_project)
app.add_typer(publish_app, name="publish")
app.add_typer(tinker_app, name="tinker")
app.add_typer(config_app, name="config")
app.command(name="down")(down)
app.command(name="up")(up)


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
