"""``lang:list`` — show the locales available under the app's ``lang/`` directory.

:func:`list_locales` (pure, testable) enumerates locale codes from ``lang/`` — both
``lang/<code>/`` directories and ``lang/<code>.json`` files. Grounded in doc 13 + doc 14.
"""

from __future__ import annotations

from pathlib import Path

import typer


def list_locales(lang_dir: Path) -> list[str]:
    """Locale codes under ``lang_dir`` (``<code>/`` dirs and ``<code>.json`` files)."""
    if not lang_dir.exists():
        return []
    codes = {
        entry.name if entry.is_dir() else entry.stem
        for entry in lang_dir.iterdir()
        if not entry.name.startswith(".") and (entry.is_dir() or entry.suffix == ".json")
    }
    return sorted(codes)


lang_app = typer.Typer()


@lang_app.command()
def lang_list() -> None:
    """List the available locales (under ./lang)."""
    locales = list_locales(Path("lang"))
    if not locales:
        typer.echo("no locales found under ./lang")
        return
    typer.echo("locales: " + ", ".join(locales))
