"""Plugin registry — discovers and lazily loads CLI command plugins."""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

import typer
import typer.core
import typer.main
import typer.models

if TYPE_CHECKING:
    from click import Command, Context

logger = logging.getLogger(__name__)

_BUILTIN: dict[str, tuple[str, str, str]] = {
    "about": ("arvel.cli.plugins.about", "_app", "Show framework information."),
    "config": ("arvel.cli.plugins.config_cmd", "_app", "Configuration cache commands."),
    "db": ("arvel.cli.plugins.db", "_app", "Database migration and seeding commands."),
    "down": ("arvel.cli.plugins.maintenance", "down", "Put the application into maintenance mode."),
    "health": ("arvel.cli.plugins.health", "_app", "Health check commands."),
    "make": ("arvel.cli.plugins.make", "_app", "Code generation commands."),
    "new": ("arvel.cli.plugins.new", "new_project", "Create a new Arvel project."),
    "publish": ("arvel.cli.plugins.publish", "_app", "Publish framework resources."),
    "queue": ("arvel.cli.plugins.queue", "_app", "Queue worker management commands."),
    "route": ("arvel.cli.plugins.route", "_app", "Route inspection commands."),
    "schedule": ("arvel.cli.plugins.schedule", "_app", "Task scheduler management commands."),
    "serve": ("arvel.cli.plugins.serve", "_serve_app", "Start the development server."),
    "tinker": ("arvel.cli.plugins.tinker", "_app", "Interactive REPL with application context."),
    "up": ("arvel.cli.plugins.maintenance", "up", "Bring the application out of maintenance mode."),
    "view": ("arvel.cli.plugins.view", "_app", "Materialized view management commands."),
}


class PluginRegistry:
    """Central registry for all CLI command plugins.

    Built-in plugins are listed in ``_BUILTIN`` by command name and module path.
    They're imported on demand — only when the user actually invokes the command.
    """

    _BUILTIN: ClassVar[dict[str, tuple[str, str, str]]] = _BUILTIN

    def __init__(self) -> None:
        self._loaded_commands: dict[str, Command] = {}

    def _import_command(self, name: str) -> Command | None:
        """Import the plugin module and resolve it to a Click command.

        Handles three cases (matching the original ``_LazyGroup._import_real``):
        1. Attribute is a ``typer.Typer`` — convert to Click group.
        2. Attribute is a callable — wrap as a Click command via Typer's ``CommandInfo``.
        3. Neither — return ``None``.
        """
        if name not in self._BUILTIN:
            return None

        if name in self._loaded_commands:
            return self._loaded_commands[name]

        module_path, attr_name, _ = self._BUILTIN[name]
        mod = importlib.import_module(module_path)
        attr = getattr(mod, attr_name, None)
        if attr is None:
            return None

        if isinstance(attr, typer.Typer):
            cmd = typer.main.get_group(attr)
            cmd.name = name
            self._loaded_commands[name] = cmd
            return cmd

        if callable(attr):
            cmd = typer.main.get_command_from_info(
                typer.models.CommandInfo(name=name, callback=attr),
                pretty_exceptions_short=True,
                rich_markup_mode=None,
            )
            self._loaded_commands[name] = cmd
            return cmd

        return None

    @staticmethod
    def builtin_names() -> list[str]:
        """Sorted list of all built-in command names."""
        return sorted(_BUILTIN)

    @staticmethod
    def help_text(name: str) -> str:
        """Help string for a built-in command (used in ``--help`` listings)."""
        _, _, help_text = _BUILTIN[name]
        return help_text

    def discover_user_commands(self, app: typer.Typer, base_path: Path | None = None) -> None:
        """Scan ``app/Console/Commands/*.py`` and register any Typer apps found.

        Called **only** by plugins that need app context (``serve``, ``tinker``),
        never at import time.
        """
        base = base_path or Path.cwd()
        commands_dir = base / "app" / "Console" / "Commands"
        if not commands_dir.is_dir():
            return

        for f in sorted(commands_dir.iterdir()):
            if not f.is_file() or f.suffix != ".py" or f.name.startswith("_"):
                continue

            module_name = f"app.Console.Commands.{f.stem}"
            spec = importlib.util.spec_from_file_location(module_name, str(f))
            if spec is None or spec.loader is None:
                continue

            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            try:
                spec.loader.exec_module(mod)
            except Exception:
                logger.warning(
                    "Failed to load command module %s: %s",
                    f.name,
                    sys.exc_info()[1],
                )
                continue

            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if isinstance(attr, typer.Typer):
                    app.add_typer(attr, name=f.stem)
                    break


class LazyPluginGroup(typer.core.TyperGroup):
    """Click group that loads plugins on demand via the ``PluginRegistry``.

    Overrides ``get_command`` and ``list_commands``. When a lazy command is
    accessed, the registry imports the plugin module and converts its Typer
    app to a Click command on the fly.
    """

    _registry: PluginRegistry

    def list_commands(self, ctx: Context) -> list[str]:
        base = super().list_commands(ctx)
        lazy = self._registry.builtin_names()
        return sorted(set(base + lazy))

    def get_command(self, ctx: Context, cmd_name: str) -> Command | None:
        cmd = super().get_command(ctx, cmd_name)
        if cmd is not None:
            return cmd

        return self._registry._import_command(cmd_name)
