"""``optimize`` and ``optimize:clear`` — run/clear all production caches."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import typer

from arvel.config._lookup_registry import dump_config_cache, reset
from arvel.console import Command, Context
from arvel.console._subsystem import CliSubsystem
from arvel.console.commands.config_commands import CONFIG_CACHE_REL
from arvel.support.view import clear_bytecode_cache, reset_cache, warm_bytecode_cache

_CONFIG_CACHE_REL = CONFIG_CACHE_REL


class OptimizeCommand(Command):
    name: ClassVar[str] = "optimize"
    help: ClassVar[str] = "Pre-compile config and view caches for production."
    requires: ClassVar[frozenset[CliSubsystem]] = frozenset({CliSubsystem.USER_PROVIDERS})

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback() -> None:
            cmd_self._run()

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    def _run(self) -> None:
        config_dest: Path = (
            self.app.base_path() / _CONFIG_CACHE_REL if self.app is not None else _CONFIG_CACHE_REL
        )
        config_count = dump_config_cache(config_dest)
        typer.echo(f"  config:cache  — {config_count} module(s) cached.")

        view_count = warm_bytecode_cache()
        typer.echo(f"  view:cache    — {view_count} template(s) compiled.")

        # No route/event cache: unlike Laravel's string actions, Arvel routes and
        # event listeners are live Python callables — they can't be serialized to
        # skip the import, and importing the module is already .pyc-cached. So the
        # cache would buy nothing. See docs research 048.
        typer.echo("  route:cache   — n/a on Python (routes import as live callables).")
        typer.echo("  event:cache   — n/a on Python (listeners import as live callables).")

        typer.echo("Optimization complete.")


class OptimizeClearCommand(Command):
    name: ClassVar[str] = "optimize:clear"
    help: ClassVar[str] = "Remove all production caches (config, views)."

    def register(self, app: typer.Typer) -> None:
        def _callback() -> None:
            _run_clear()

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError


def _run_clear() -> None:
    config_path = _CONFIG_CACHE_REL
    if config_path.exists():
        config_path.unlink()
        typer.echo(f"  config:clear  — removed {config_path}.")
    else:
        typer.echo("  config:clear  — nothing to clear.")
    reset()

    clear_bytecode_cache()
    reset_cache()
    typer.echo("  view:clear    — cleared.")

    typer.echo("Cache clear complete.")


__all__ = ["OptimizeClearCommand", "OptimizeCommand"]
