"""storage:link CLI command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from arvel.console import Command, Context
from arvel.console._t import Option as _Option


class StorageLinkCommand(Command):
    name = "storage:link"
    help = "Create a symbolic link from public/storage to storage/app/public"

    def register(self, app: typer.Typer) -> None:
        def _callback(
            *,
            relative: Annotated[bool, _Option("--relative", help="Use a relative symlink")] = False,
        ) -> None:
            target = Path("storage/app/public")
            link = Path("public/storage")

            target.mkdir(parents=True, exist_ok=True)
            link.parent.mkdir(parents=True, exist_ok=True)

            if link.exists() or link.is_symlink():
                typer.echo(f"Link already exists: {link}")
                return

            if relative:
                link.symlink_to(Path("../../storage/app/public"))
            else:
                link.symlink_to(target.resolve())

            typer.echo(f"Linked {link} → {target}")

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError
