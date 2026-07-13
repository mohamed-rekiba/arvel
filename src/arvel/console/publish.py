"""``vendor:publish`` — copy publishable resources into the app.

Service providers register publishable files (config, assets, migrations) via ``self.publishes({src:
dest}, tag=...)`` / ``publishes_migrations(...)``, recorded in the ``console.published``
registry (``{tag: {src: dest}}``). This command copies them into the app, optionally filtered by ``--tag`` and overwriting with
``--force``. Imports stay light (typer only); the app is booted via the console kernel at runtime.
Grounded in knowledge/port/13-console.md.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import typer

vendor_publish_app = typer.Typer()


@vendor_publish_app.command()
def vendor_publish(
    tag: str = typer.Option(
        None, "--tag", help="Only publish resources registered under this tag."
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite destination files that exist."),
) -> None:
    """Publish package resources (config, assets, migrations) registered by providers into your app."""
    from arvel.console.kernel import run_app_command

    async def _run(app: Any) -> None:
        _publish(app, tag, force)

    run_app_command(_run)


def _publish(app: Any, tag: str | None, force: bool) -> None:
    """Copy the registered publishable resources (optionally a single ``tag``) into the app."""
    published: dict[str, dict[str, str]] = app.registry("console.published", dict)
    if tag is not None:
        if tag not in published:
            typer.echo(f"[vendor:publish] no resources registered under tag {tag!r}")
            raise typer.Exit(1)
        groups = {tag: published[tag]}
    else:
        groups = published
    if not any(groups.values()):
        typer.echo(
            "[vendor:publish] nothing to publish (no provider registered publishable resources)"
        )
        return
    published_count = 0
    for mapping in groups.values():
        for src, dest in mapping.items():
            status = _copy(Path(src), Path(dest), force=force)
            if status == "published":
                published_count += 1
                typer.echo(f"  published {dest}")
            elif status == "exists":
                typer.echo(f"  skipped  {dest} (exists; pass --force to overwrite)")
            else:
                typer.echo(f"  WARNING  source not found, skipped: {src}")
    typer.echo(f"[vendor:publish] published {published_count} item(s)")


def _copy(src: Path, dest: Path, *, force: bool) -> str:
    """Copy ``src``→``dest`` (file or directory tree). Returns ``published`` | ``exists`` | ``missing``;
    refuses to overwrite an existing destination unless ``force``."""
    if not src.exists():
        return "missing"
    if dest.exists() and not force:
        return "exists"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dest, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dest)
    return "published"
