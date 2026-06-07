"""``vendor:publish`` — copy package-shipped files into the consumer app.

Mirrors Laravel's ``php artisan vendor:publish``. Walks the
:class:`~arvel.support.publishing.PublishRegistry` populated by every
:class:`~arvel.providers.ServiceProvider` that called ``self.publishes(...)``
in its ``boot()``, then copies each registered file into its destination.

Migration files (``is_migration=True``) get their basename rewritten with
a UTC timestamp at publish time so they slot into ``database/migrations/``
in chronological order. Plain config / asset publishes are copied as-is.

Exit codes
----------
- 0 — success (work done, or nothing matched the filters)
- 1 — a copy failed (permission, disk full, etc.)
- 2 — bootstrap failed (no Application, no PublishRegistry)
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated, ClassVar

import typer

from arvel.console import Command, Context
from arvel.console._subsystem import CliSubsystem
from arvel.console._t import Option as _Option
from arvel.support.publishing import (
    Publishable,
    PublishRegistry,
    rewrite_migration_filename,
)


class VendorPublishCommand(Command):
    name: ClassVar[str] = "vendor:publish"
    help: ClassVar[str] = "Publish package files (migrations, config, assets) into the app"
    # PublishRegistry is populated during the user's provider boot(), so we
    # need the full user provider chain — not just config/foundation.
    requires: ClassVar[frozenset[CliSubsystem]] = frozenset({CliSubsystem.USER_PROVIDERS})

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            *,
            provider: Annotated[
                str | None,
                _Option("--provider", help="Filter by provider class name (FQN or bare)."),
            ] = None,
            tag: Annotated[
                str | None,
                _Option("--tag", help="Filter by publish tag."),
            ] = None,
            force: Annotated[
                bool,
                _Option("--force", help="Overwrite destination files that already exist."),
            ] = False,
        ) -> None:
            code = cmd_self.publish(provider=provider, tag=tag, force=force)
            if code != 0:
                raise typer.Exit(code)

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    def publish(self, *, provider: str | None, tag: str | None, force: bool) -> int:
        return self._publish(provider=provider, tag=tag, force=force)

    def _publish(self, *, provider: str | None, tag: str | None, force: bool) -> int:
        if self.app is None:
            typer.echo("arvel: vendor:publish requires a framework Application", err=True)
            return 2

        try:
            registry: PublishRegistry = self.app.container.make(PublishRegistry)
        except Exception as exc:  # noqa: BLE001 — surface bootstrap failures with exit 2
            typer.echo(f"arvel: PublishRegistry not bound: {exc}", err=True)
            return 2

        items = self._filter(registry.all(), provider=provider, tag=tag)
        if not items:
            typer.echo("Nothing to publish.")
            return 0

        used_destinations: set[Path] = set()
        copied = 0
        skipped: list[Path] = []
        try:
            for item in items:
                target = self._target_path(item, used=used_destinations)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() and not force:
                    skipped.append(target)
                    continue
                shutil.copyfile(item.source, target)
                copied += 1
        except OSError as exc:
            typer.echo(f"arvel: vendor:publish failed: {exc}", err=True)
            return 1

        if copied:
            typer.echo(f"Published {copied} file(s).")
        for path in skipped:
            typer.echo(f"Skipped (already exists, use --force): {path}")
        return 0

    @staticmethod
    def _filter(
        items: list[Publishable],
        *,
        provider: str | None,
        tag: str | None,
    ) -> list[Publishable]:
        out = items
        if provider is not None:
            bare = provider.rsplit(".", 1)[-1]
            out = [
                p for p in out if p.provider == provider or p.provider.rsplit(".", 1)[-1] == bare
            ]
        if tag is not None:
            out = [p for p in out if p.tag == tag]
        return out

    @staticmethod
    def _target_path(item: Publishable, *, used: set[Path]) -> Path:
        if not item.is_migration:
            return item.destination
        return rewrite_migration_filename(item.source, item.destination, used=used)


__all__ = ["VendorPublishCommand"]
