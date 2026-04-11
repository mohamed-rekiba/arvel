"""Config cache and export — serialize settings to JSON for faster boot."""

from __future__ import annotations

import asyncio
import inspect
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

if TYPE_CHECKING:
    from arvel.cli.plugins._base import CliPlugin

_app = typer.Typer(name="config", help="Configuration cache commands.")


def _cache_path() -> Path:
    return Path.cwd() / "bootstrap" / "cache" / "config.json"


def _render_config_file(settings_cls: type[object], _file_stem: str) -> str:
    """Copy framework config module source verbatim as a rendered file."""
    module = sys.modules.get(settings_cls.__module__)
    if module is None:
        raise ValueError(f"Module not loaded for {settings_cls.__module__}")

    source = inspect.getsource(module)
    return f"{source.rstrip()}\n"


@_app.command("cache")
def cache_config() -> None:
    """Write config to a JSON cache file (0600 permissions)."""
    from arvel.foundation.config import cache_config as _cache
    from arvel.foundation.config import load_config

    base_path = Path.cwd()
    config = asyncio.run(load_config(base_path))

    cache_file = _cache_path()
    cache_file.parent.mkdir(parents=True, exist_ok=True)

    _cache(config, cache_file)
    cache_file.chmod(0o600)

    typer.echo(f"Configuration cached to {cache_file}")


@_app.command("clear")
def clear_config() -> None:
    """Delete the cached config file."""
    cache_file = _cache_path()
    if cache_file.exists():
        cache_file.unlink()
        typer.echo("Configuration cache cleared.")
    else:
        typer.echo("No configuration cache to clear.")


@_app.command("export")
def export(
    path: Annotated[Path, typer.Option(help="Target config directory.")] = Path("config"),
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show planned changes only.")] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite existing config files.")
    ] = False,
) -> None:
    """Export framework default config files. Skips existing unless --force."""
    from arvel.app.config import AppSettings
    from arvel.foundation.config import default_module_settings, settings_file_candidates

    target_dir = path if path.is_absolute() else Path.cwd() / path
    target_dir.mkdir(parents=True, exist_ok=True)

    created: list[Path] = []
    skipped: list[Path] = []

    export_payloads: dict[str, str] = {}

    for settings_cls in default_module_settings():
        candidates = settings_file_candidates(settings_cls)
        if not candidates:
            continue
        file_stem = candidates[0]
        export_payloads[file_stem] = _render_config_file(settings_cls, file_stem)
    export_payloads["app"] = _render_config_file(AppSettings, "app")

    for file_stem, rendered_content in export_payloads.items():
        config_path = target_dir / f"{file_stem}.py"
        if config_path.exists() and not force:
            skipped.append(config_path)
            continue

        if dry_run:
            created.append(config_path)
            continue

        config_path.write_text(rendered_content)
        created.append(config_path)

    if created:
        action = "Would create" if dry_run else "Created"
        typer.echo(f"{action}:")
        for config_path in created:
            typer.echo(f"- {config_path}")
    else:
        typer.echo("No config files created.")

    if skipped:
        typer.echo("Skipped existing:")
        for config_path in skipped:
            typer.echo(f"- {config_path}")


class _Plugin:
    name = "config"
    help = "Configuration cache commands."

    def register(self, app: typer.Typer) -> None:
        app.add_typer(_app, name=self.name)


plugin: CliPlugin = _Plugin()  # type: ignore[assignment]
