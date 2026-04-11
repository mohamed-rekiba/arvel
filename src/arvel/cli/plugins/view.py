"""Materialized view management — refresh one or all views."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import typer

from arvel.data.config import DatabaseSettings

if TYPE_CHECKING:
    from arvel.cli.plugins._base import CliPlugin

_app = typer.Typer(name="view", help="Materialized view management commands.")


@_app.command()
def refresh(
    name: str | None = typer.Argument(None, help="View name to refresh."),
    all_views: bool = typer.Option(False, "--all", help="Refresh all views."),
) -> None:
    """Refresh a materialized view (or all views with --all)."""
    from arvel.data.materialized_view import ViewRegistry

    settings = DatabaseSettings()
    registry = ViewRegistry()

    if all_views:
        results = asyncio.run(registry.refresh_all(db_url=settings.url))
        for r in results:
            typer.echo(f"  Refreshed: {r['view']} ({r['status']})")
    elif name:
        result = asyncio.run(registry.refresh(name, db_url=settings.url))
        typer.echo(f"  Refreshed: {result['view']} ({result['status']})")
    else:
        typer.echo("Specify a view name or use --all.")
        raise typer.Exit(code=1)


class _Plugin:
    name = "view"
    help = "Materialized view management commands."

    def register(self, app: typer.Typer) -> None:
        app.add_typer(_app, name=self.name)


plugin: CliPlugin = _Plugin()  # type: ignore[assignment]
