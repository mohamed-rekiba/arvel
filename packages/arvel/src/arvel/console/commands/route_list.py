"""route:list command — print every registered route in a five-column table.

Pulls routes straight from ``arvel.routing.Router.singleton()`` so the
command works whether or not the application has bound a router into the
container. Columns mirror Laravel's ``php artisan route:list``: Method,
URI, Name, Action (``Controller#method`` or callable qualname), Middleware.

Two switches:

``--filter <substring>``
    Case-insensitive substring match against the path. Useful for narrowing
    down to a single domain (``--filter api`` keeps only ``/api/...`` routes).

``--json``
    Emit a JSON array — one object per route — for piping into ``jq`` or
    other tooling. Honours ``--filter``.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, ClassVar

import typer

from arvel.console import Command, Context
from arvel.console._subsystem import CliSubsystem
from arvel.console._t import Option as _Option
from arvel.routing import Router, RouteSpec


def _format_action(spec: RouteSpec) -> str:
    """Pick the most informative label for the Action column.

    - Controller + named method → ``Controller#method`` (Laravel-style)
    - Invokable controller (defines ``__call__``) → ``Controller#__call__``
    - Plain function handler → ``handler.__qualname__``
    """
    controller = spec.controller
    if controller is not None:
        action = spec.action or "__call__"
        return f"{controller.__name__}#{action}"
    handler = spec.handler
    return str(getattr(handler, "__qualname__", repr(handler)))


def _format_middleware(spec: RouteSpec) -> str:
    """Comma-joined middleware class names; ``"-"`` when the tuple is empty."""
    if not spec.middleware:
        return "-"
    return ", ".join(type(mw).__name__ for mw in spec.middleware)


def _filter_routes(routes: list[RouteSpec], needle: str | None) -> list[RouteSpec]:
    if not needle:
        return routes
    lowered = needle.lower()
    return [r for r in routes if lowered in r.path.lower()]


def _route_to_dict(spec: RouteSpec) -> dict[str, Any]:
    return {
        "method": spec.method,
        "path": spec.path,
        "name": spec.name,
        "action": _format_action(spec),
        "middleware": [type(mw).__name__ for mw in spec.middleware],
    }


def _print_table(routes: list[RouteSpec]) -> None:
    headers = ("Method", "URI", "Name", "Action", "Middleware")
    rows: list[tuple[str, str, str, str, str]] = [
        (
            spec.method,
            spec.path,
            spec.name or "-",
            _format_action(spec),
            _format_middleware(spec),
        )
        for spec in routes
    ]

    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    line_parts = [headers[i].ljust(widths[i]) for i in range(len(headers))]
    typer.echo("  ".join(line_parts).rstrip())
    typer.echo("-" * (sum(widths) + 2 * (len(widths) - 1)))
    for row in rows:
        cells = [row[i].ljust(widths[i]) for i in range(len(row))]
        typer.echo("  ".join(cells).rstrip())


class RouteListCommand(Command):
    name: ClassVar[str] = "route:list"
    help: ClassVar[str] = "List all registered routes (method, URI, name, action, middleware)"
    requires: ClassVar[frozenset[CliSubsystem]] = frozenset(
        {CliSubsystem.HTTP, CliSubsystem.USER_PROVIDERS}
    )

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            *,
            filter_: Annotated[
                str | None,
                _Option(
                    "--filter",
                    help="Case-insensitive substring filter applied to the route path.",
                ),
            ] = None,
            as_json: Annotated[
                bool,
                _Option(
                    "--json",
                    help="Emit raw JSON instead of the human-readable table.",
                ),
            ] = False,
        ) -> None:
            routes = _filter_routes(cmd_self.get_routes(), filter_)

            if as_json:
                typer.echo(json.dumps([_route_to_dict(r) for r in routes]))
                return

            if not routes:
                if filter_:
                    typer.echo(f"(no routes match filter {filter_!r})")
                else:
                    typer.echo("(no routes registered)")
                return

            _print_table(routes)

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    def get_routes(self) -> list[RouteSpec]:
        """All routes currently buffered by the application's ``Router``.

        Prefers the router bound in the framework container (contract).
        Falls back to ``Router.singleton`` when no application is attached or
        the container has no Router binding — covers bare test contexts where
        no provider has booted but routes were declared directly against the
        singleton.
        """
        if self.app is not None:
            try:
                router = self.app.container.make(Router)
            except Exception:  # noqa: BLE001 — any container failure falls back to singleton
                router = None
            if router is not None:
                return router.routes()
        return Router.singleton().routes()
