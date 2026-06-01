"""model:show command."""

from __future__ import annotations

import importlib
from typing import Annotated, ClassVar

import typer

from arvel.console import Command, Context
from arvel.console._t import Argument as _Argument


class ModelShowCommand(Command):
    name: ClassVar[str] = "model:show"
    help: ClassVar[str] = "Print model metadata (table, attributes, visible/hidden)"

    def register(self, app: typer.Typer) -> None:
        def _callback(
            path: Annotated[str, _Argument(help="Dotted model path, e.g. app.models.User")],
        ) -> None:
            module_path, _, class_name = path.rpartition(".")
            if not module_path:
                typer.echo(f"arvel: '{path}' is not a dotted path.", err=True)
                raise typer.Exit(code=2)
            try:
                module = importlib.import_module(module_path)
                cls = getattr(module, class_name)
            except (ImportError, AttributeError) as exc:
                typer.echo(f"arvel: cannot import {path}: {exc}", err=True)
                raise typer.Exit(code=2) from exc

            typer.echo(f"Model:   {cls.__name__}")
            typer.echo(f"Table:   {getattr(cls, 'table', '?')}")
            annotations = getattr(cls, "__annotations__", {})
            typer.echo("Attributes:")
            for attr_name, attr_type in annotations.items():
                typer.echo(f"  - {attr_name}: {attr_type}")
            typer.echo(f"Visible: {list(getattr(cls, 'visible', []))}")
            typer.echo(f"Hidden:  {list(getattr(cls, 'hidden', []))}")

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError
