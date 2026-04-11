"""Route commands — list, cache, and clear the route table."""

from __future__ import annotations

import json as json_lib
from pathlib import Path
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from arvel.cli.plugins._base import CliPlugin

_app = typer.Typer(name="route", help="Route inspection commands.")


def _route_cache_path() -> Path:
    return Path.cwd() / "bootstrap" / "cache" / "routes.json"


@_app.command("list")
def list_routes(
    app_dir: str = typer.Option(".", "--app-dir", help="Application root directory."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Print all registered routes."""
    from arvel.http.router import discover_routes

    base_path = Path(app_dir).resolve()
    routers = discover_routes(base_path)

    rows = []
    for _mod_name, router in routers:
        for entry in router.route_entries:
            rows.append(
                {
                    "method": ", ".join(sorted(entry.methods)),
                    "uri": entry.path,
                    "name": entry.name or "",
                    "middleware": ", ".join(entry.middleware) if entry.middleware else "",
                }
            )

    if json:
        typer.echo(json_lib.dumps(rows, indent=2))
        return

    if not rows:
        typer.echo("No routes registered.")
        return

    typer.echo(f"{'Method':<10} {'URI':<40} {'Name':<25} {'Middleware'}")
    typer.echo("-" * 90)
    for row in rows:
        typer.echo(f"{row['method']:<10} {row['uri']:<40} {row['name']:<25} {row['middleware']}")


def _collect_route_data(base_path: Path) -> list[dict[str, object]]:
    """Gather route data from all modules as plain dicts."""
    from arvel.http.router import discover_routes

    routers = discover_routes(base_path)
    rows: list[dict[str, object]] = []
    for _mod_name, router in routers:
        for entry in router.route_entries:
            rows.append(
                {
                    "path": entry.path,
                    "methods": sorted(entry.methods),
                    "name": entry.name or "",
                    "middleware": entry.middleware if entry.middleware else [],
                }
            )
    return rows


@_app.command("cache")
def cache_routes(
    app_dir: str = typer.Option(".", "--app-dir", help="Application root directory."),
) -> None:
    """Write the route table to a JSON cache for faster boot."""
    base_path = Path(app_dir).resolve()
    rows = _collect_route_data(base_path)

    cache_file = _route_cache_path()
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json_lib.dumps(rows, indent=2))

    typer.echo(f"Route cache written to {cache_file} ({len(rows)} routes)")


@_app.command("clear")
def clear_routes() -> None:
    """Delete the cached route table."""
    cache_file = _route_cache_path()
    if cache_file.exists():
        cache_file.unlink()
        typer.echo("Route cache cleared.")
    else:
        typer.echo("No route cache to clear.")


class _Plugin:
    name = "route"
    help = "Route inspection commands."

    def register(self, app: typer.Typer) -> None:
        app.add_typer(_app, name=self.name)


plugin: CliPlugin = _Plugin()  # type: ignore[assignment]
