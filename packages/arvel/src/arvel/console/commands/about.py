"""about command — prints framework and runtime information."""

from __future__ import annotations

import importlib.metadata
import sys

import typer

from arvel.console import Command, Context


class AboutCommand(Command):
    name = "about"
    help = "Display arvel framework information"

    def register(self, app: typer.Typer) -> None:
        def _callback() -> None:
            try:
                version = importlib.metadata.version("arvel")
            except importlib.metadata.PackageNotFoundError:
                version = "dev"

            py = sys.version_info
            typer.echo(f"arvel {version}")
            typer.echo(f"Python {py.major}.{py.minor}.{py.micro}")

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError
