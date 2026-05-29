"""storage:unlink CLI command — counterpart to storage:link."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import typer

from arvel.console import Command, Context


class StorageUnlinkCommand(Command):
    name: ClassVar[str] = "storage:unlink"
    help: ClassVar[str] = "Remove the public/storage symlink (idempotent)"

    def register(self, app: typer.Typer) -> None:
        def _callback() -> None:
            link = Path("public/storage")
            if link.is_symlink() or link.exists():
                try:
                    link.unlink()
                    typer.echo(f"Removed symlink: {link}")
                except OSError as exc:
                    typer.echo(f"arvel: cannot remove {link}: {exc}", err=True)
                    raise typer.Exit(code=2) from exc
            else:
                typer.echo(f"No symlink at {link}.")

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError
