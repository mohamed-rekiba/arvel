"""view:* console commands."""

from __future__ import annotations

from typing import ClassVar

import typer

from arvel.console import Command, Context
from arvel.support.view import clear_bytecode_cache, reset_cache, warm_bytecode_cache


class ViewCacheCommand(Command):
    name: ClassVar[str] = "view:cache"
    help: ClassVar[str] = "Pre-compile all Jinja templates into bootstrap/views/."

    def register(self, app: typer.Typer) -> None:
        def _callback() -> None:
            count = warm_bytecode_cache()
            typer.echo(f"Compiled {count} template(s) into bootstrap/views/.")

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError


class ViewClearCommand(Command):
    name: ClassVar[str] = "view:clear"
    help: ClassVar[str] = "Clear the cached Jinja environment and bytecode cache"

    def register(self, app: typer.Typer) -> None:
        def _callback() -> None:
            clear_bytecode_cache()
            reset_cache()
            typer.echo("View cache cleared.")

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError


__all__ = ["ViewCacheCommand", "ViewClearCommand"]
