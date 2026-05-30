"""down + up commands (WI-arvel-023)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, ClassVar

import typer

from arvel.console import Command, Context
from arvel.console._t import Option as _Option
from arvel.maintenance import MaintenanceModeManager


def _resolve_manager() -> MaintenanceModeManager:
    """Construct a manager rooted at the current working directory."""
    return MaintenanceModeManager(marker_path=Path("storage/framework/down"))


class DownCommand(Command):
    name: ClassVar[str] = "down"
    help: ClassVar[str] = "Put the application into maintenance mode"

    def register(self, app: typer.Typer) -> None:
        def _callback(
            *,
            secret: Annotated[str, _Option("--secret", help="Bypass token")] = "",
            retry: Annotated[int, _Option("--retry", help="Retry-After value in seconds")] = 0,
            refresh: Annotated[int, _Option("--refresh", help="Refresh header value")] = 0,
            render: Annotated[
                str,
                _Option("--render", help="Template path to render instead of plain text"),
            ] = "",
        ) -> None:
            manager = _resolve_manager()
            marker = manager.down(
                secret=secret or None,
                retry=retry or None,
                refresh=refresh or None,
                template=render or None,
            )
            typer.echo("Application is now in maintenance mode.")
            typer.echo(f"Bypass token: {marker.secret}")

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError


class UpCommand(Command):
    name: ClassVar[str] = "up"
    help: ClassVar[str] = "Bring the application out of maintenance mode"

    def register(self, app: typer.Typer) -> None:
        def _callback() -> None:
            manager = _resolve_manager()
            manager.up()
            typer.echo("Application is now live.")

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError
