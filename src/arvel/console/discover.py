"""``package:discover`` — rebuild the cached package manifest (doc 13 §cached discovery)."""

from __future__ import annotations

import typer

discover_app = typer.Typer()


@discover_app.command()
def package_discover() -> None:
    """Scan ``arvel.providers`` entry points and write ``bootstrap/cache/packages.py``."""
    from arvel.kernel.discovery import clear_cache, write_manifest

    path = write_manifest()
    clear_cache()  # drop the in-process cache so the next resolve reads the fresh manifest
    typer.echo(f"[package:discover] wrote {path}")
