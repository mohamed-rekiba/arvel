"""``route:list`` — tabulate the application's registered routes.

The pure formatter (:func:`format_routes`) is unit-testable; the command resolves the
router from the booted application. Grounded in knowledge/port/13-console.md.
"""

from __future__ import annotations

from typing import Any

import typer


def format_routes(routes: list[Any]) -> str:
    """Render route definitions as an aligned ``METHODS  PATH  NAME`` table."""
    rows = [
        ("|".join(route.methods), route.path, getattr(route, "name", None) or "")
        for route in routes
    ]
    if not rows:
        return "(no routes registered)"
    method_w = max(len(methods) for methods, _, _ in rows)
    path_w = max(len(path) for _, path, _ in rows)
    return "\n".join(
        f"{methods:<{method_w}}  {path:<{path_w}}  {name}".rstrip() for methods, path, name in rows
    )


route_list_app = typer.Typer()


@route_list_app.command()
def route_list() -> None:
    """List the application's registered routes."""
    from arvel.console.kernel import run_app_command

    run_app_command(_route_list)


async def _route_list(app: Any) -> None:
    """Print the booted app's routes (run inside the console kernel's app lifecycle)."""
    typer.echo(format_routes(app.make("router").routes()))
