"""Arvel CLI — main Typer application.

Registers built-in command plugins via :class:`PluginRegistry` and discovers
user-defined commands from ``app/Console/Commands/`` on demand.
"""

from __future__ import annotations

import typer

from arvel.cli.registry import LazyPluginGroup, PluginRegistry
from arvel.cli.ui import BANNER

registry = PluginRegistry()
LazyPluginGroup._registry = registry

app = typer.Typer(
    name="arvel",
    help="Arvel framework CLI — migrations, seeders, generators, queue, scheduler.",
    no_args_is_help=True,
    cls=LazyPluginGroup,
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
