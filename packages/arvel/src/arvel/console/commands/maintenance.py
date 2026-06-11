"""down + up commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, ClassVar

import typer

from arvel.console import Command, Context
from arvel.console._t import Option as _Option
from arvel.maintenance import MaintenanceModeManager


def _resolve_manager(cmd: Command) -> MaintenanceModeManager:
    """Construct a manager rooted at the project base_path.

    Matches the path the running app uses (``HttpServiceProvider`` roots the
    bound manager at ``base_path``), so a CLI ``down`` engages the marker the
    HTTP middleware actually checks — regardless of the shell's CWD.
    """
    root = cmd.app.base_path() if cmd.app is not None else Path.cwd()
    return MaintenanceModeManager(marker_path=root / "storage" / "framework" / "down")


class DownCommand(Command):
    name: ClassVar[str] = "down"
    help: ClassVar[str] = "Put the application into maintenance mode"
    requires_project_context: ClassVar[bool] = True

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

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
            manager = _resolve_manager(cmd_self)
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
    requires_project_context: ClassVar[bool] = True

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback() -> None:
            manager = _resolve_manager(cmd_self)
            manager.up()
            typer.echo("Application is now live.")

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError
