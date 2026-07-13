"""``package:discover`` — rebuild the cached package manifest (doc 13 §cached discovery)."""

from __future__ import annotations

import typer

discover_app = typer.Typer()


@discover_app.command()
def package_discover() -> None:
    """Scan ``arvel.providers`` entry points and write ``bootstrap/cache/packages.py``."""
    from pathlib import Path

    from arvel.kernel.discovery import clear_cache, write_manifest

    # same "run inside a project" contract as app-loading commands — otherwise the
    # manifest lands in a random cwd while boot reads it from the app root
    if not (Path.cwd() / "bootstrap" / "app.py").is_file():
        typer.echo("not inside an arvel project (no bootstrap/app.py) — run from the project root")
        raise typer.Exit(code=1)
    path = write_manifest()
    clear_cache()  # drop the in-process cache so the next resolve reads the fresh manifest
    typer.echo(f"[package:discover] wrote {path}")
