"""event:list command (WI-arvel-023)."""

from __future__ import annotations

from typing import ClassVar

import typer

from arvel.console import Command, Context
from arvel.container.errors import BindingResolutionError
from arvel.events.dispatcher import EventDispatcher


class EventListCommand(Command):
    name: ClassVar[str] = "event:list"
    help: ClassVar[str] = "List registered events and their listeners"
    needs_application: ClassVar[bool] = True

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback() -> None:
            if cmd_self.app is None:
                typer.echo("arvel: event subsystem not registered.", err=True)
                raise typer.Exit(code=2)
            try:
                dispatcher = cmd_self.app.container.make(EventDispatcher)
            except BindingResolutionError as exc:
                typer.echo(f"arvel: {exc}", err=True)
                raise typer.Exit(code=2) from exc
            all_listeners = dispatcher.all_listeners()
            if not all_listeners:
                typer.echo("(no listeners registered)")
                return
            for event_cls, listeners in all_listeners.items():
                event_name = getattr(event_cls, "__name__", str(event_cls))
                typer.echo(f"{event_name}:")
                for listener in listeners:
                    name = getattr(listener, "__name__", str(listener))
                    typer.echo(f"  - {name}")

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError
