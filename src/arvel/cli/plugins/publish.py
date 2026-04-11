"""Copy built-in stub templates into the project for customization."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from arvel.cli.templates.engine import builtin_template_names

if TYPE_CHECKING:
    from arvel.cli.plugins._base import CliPlugin

_app = typer.Typer(name="publish", help="Publish framework resources.")


@_app.command("stubs")
def stubs(
    force: bool = typer.Option(False, "--force", help="Overwrite existing stubs."),
) -> None:
    """Publish all built-in stubs to stubs/. Skips existing unless --force."""
    from arvel.cli.templates.engine import _builtin_stubs_dir

    source = _builtin_stubs_dir()
    target = Path.cwd() / "stubs"
    target.mkdir(parents=True, exist_ok=True)

    copied = 0
    skipped = 0
    for template_name in builtin_template_names():
        src = source / template_name
        dst = target / template_name
        if dst.exists() and not force:
            skipped += 1
            typer.echo(f"  SKIP  {template_name} (exists, use --force to overwrite)")
            continue
        shutil.copy2(src, dst)
        copied += 1
        typer.echo(f"  COPY  {template_name}")

    typer.echo(f"\nPublished {copied} stubs to {target}")
    if skipped:
        typer.echo(f"Skipped {skipped} existing stubs (use --force to overwrite)")


class _Plugin:
    name = "publish"
    help = "Publish framework resources."

    def register(self, app: typer.Typer) -> None:
        app.add_typer(_app, name=self.name)


plugin: CliPlugin = _Plugin()  # type: ignore[assignment]
