"""Materialized view CLI commands: view:refresh."""

from __future__ import annotations

import asyncio

import typer

from arvel.data.config import DatabaseSettings

view_app = typer.Typer(name="view", help="Materialized view management commands.")


@view_app.command()
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
