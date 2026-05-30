"""channel:list command (WI-arvel-023)."""

from __future__ import annotations

from typing import ClassVar

import typer

from arvel.broadcasting.exceptions import BroadcastDriverError
from arvel.broadcasting.manager import BroadcastManager
from arvel.console import Command, Context
from arvel.container.errors import BindingResolutionError


class ChannelListCommand(Command):
    name: ClassVar[str] = "channel:list"
    help: ClassVar[str] = "List registered broadcasting channels"
    needs_application: ClassVar[bool] = True

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback() -> None:
            if cmd_self.app is None:
                typer.echo(
                    "arvel: broadcasting subsystem not registered (no Application bound).",
                    err=True,
                )
                raise typer.Exit(code=2)
            try:
                manager = cmd_self.app.container.make(BroadcastManager)
            except (BindingResolutionError, BroadcastDriverError) as exc:
                typer.echo(f"arvel: {exc}", err=True)
                raise typer.Exit(code=2) from exc
            channels = manager.channels()
            if not channels:
                typer.echo("(none registered)")
                return
            typer.echo("Channels:")
            for name, handler in channels.items():
                handler_name = getattr(handler, "__name__", str(handler))
                typer.echo(f"  - {name}: {handler_name}")

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError
