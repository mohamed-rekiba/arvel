"""``oauth:install`` — publish the oauth_accounts migration."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated, ClassVar

import typer
from arvel.console import Command, Context
from arvel.console._subsystem import CliSubsystem
from arvel.console._t import Option as _Option
from arvel.support.publishing import PublishRegistry, rewrite_migration_filename

_OAUTH_TAG = "arvel-oauth"


class OAuthInstallCommand(Command):
    """Publish the oauth_accounts migration into the application."""

    name: ClassVar[str] = "oauth:install"
    help: ClassVar[str] = "Publish arvel-oauth migrations into the application"
    requires: ClassVar[frozenset[CliSubsystem]] = frozenset({CliSubsystem.USER_PROVIDERS})

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            *,
            force: Annotated[
                bool,
                _Option("--force", help="Overwrite existing files."),
            ] = False,
        ) -> None:
            code = cmd_self.install(force=force)
            if code != 0:
                raise typer.Exit(code)

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    def install(self, *, force: bool) -> int:
        if self.app is None:
            typer.echo("arvel: oauth:install requires a framework Application", err=True)
            return 2

        try:
            registry: PublishRegistry = self.app.container.make(PublishRegistry)
        except Exception as exc:  # noqa: BLE001
            typer.echo(f"arvel: PublishRegistry not bound: {exc}", err=True)
            return 2

        items = [i for i in registry.all() if i.tag == _OAUTH_TAG]
        if not items:
            typer.echo("Nothing to publish (arvel-oauth not registered).")
            return 0

        used_destinations: set[Path] = set()
        copied = 0
        skipped: list[Path] = []

        try:
            for item in items:
                if item.is_migration:
                    target = rewrite_migration_filename(
                        item.source, item.destination, used=used_destinations
                    )
                else:
                    target = item.destination
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() and not force:
                    skipped.append(target)
                    continue
                shutil.copyfile(item.source, target)
                copied += 1
        except OSError as exc:
            typer.echo(f"arvel: oauth:install failed: {exc}", err=True)
            return 1

        if copied:
            typer.echo(f"Published {copied} file(s).")
        for path in skipped:
            typer.echo(f"Skipped (exists, use --force): {path}")
        return 0


__all__ = ["OAuthInstallCommand"]
