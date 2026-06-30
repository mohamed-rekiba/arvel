"""Ops commands — Laravel parity: ``key:generate``, ``storage:link``, ``cache:clear``.

``key:generate`` / ``storage:link`` are filesystem-only (no app boot — they work in a fresh project);
``cache:clear`` resolves the bound cache and flushes it inside the booted app. Each is a single-command
``typer.Typer`` mounted lazily by ``LazyGroup``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer


def _set_env_var(path: Path, name: str, value: str) -> None:
    """Set ``NAME=value`` in a dotenv file — replace an existing line or append, preserving the rest."""
    lines = path.read_text().splitlines() if path.exists() else []
    prefix = f"{name}="
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = f"{name}={value}"
            break
    else:
        lines.append(f"{name}={value}")
    path.write_text("\n".join(lines) + "\n")


key_generate_app = typer.Typer()


@key_generate_app.command()
def key_generate() -> None:
    """Generate an app encryption key and write it to .env as APP_KEY (Laravel `key:generate`)."""
    from arvel.security import Encrypter

    key = Encrypter.generate_key()
    _set_env_var(Path(".env"), "APP_KEY", key)
    typer.echo("APP_KEY set in .env")


storage_link_app = typer.Typer()


@storage_link_app.command()
def storage_link() -> None:
    """Symlink public/storage → storage/app/public so stored files are web-served (Laravel
    `storage:link`)."""
    link = Path("public/storage")
    target = Path("storage/app/public")
    target.mkdir(parents=True, exist_ok=True)
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() or link.exists():
        typer.echo(f"{link} already exists")
        raise typer.Exit(1)
    link.symlink_to(Path("..") / target)
    typer.echo(f"linked {link} → {target}")


cache_clear_app = typer.Typer()


@cache_clear_app.command()
def cache_clear() -> None:
    """Flush the default cache store (Laravel `cache:clear`)."""
    from arvel.console.kernel import run_app_command

    run_app_command(_cache_clear)


async def _cache_clear(app: Any) -> None:
    await app.make("cache").flush()
    typer.echo("cache cleared")
