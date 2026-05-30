"""config:* console commands."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Annotated, ClassVar

import typer

from arvel.config import ConfigKeyError, lookup
from arvel.config._lookup_registry import dump_config_cache, reset
from arvel.console import Command, Context
from arvel.console._t import Argument as _Argument
from arvel.console._t import Option as _Option
from arvel.console.commands.vendor_publish import VendorPublishCommand

CONFIG_CACHE_REL = Path("bootstrap") / "cache" / "config.json"


def _format_config_value(value: object) -> str:
    try:
        return json.dumps(value, indent=2, sort_keys=True, default=str)
    except TypeError:
        return repr(value)


class ConfigShowCommand(Command):
    name: ClassVar[str] = "config:show"
    help: ClassVar[str] = "Print a resolved dotted config value"

    def register(self, app: typer.Typer) -> None:
        def _callback(
            key: Annotated[str, _Argument(help="Dotted config key, e.g. app.NAME")],
        ) -> None:
            try:
                typer.echo(_format_config_value(lookup(key)))
            except ConfigKeyError as exc:
                typer.echo(f"arvel: {exc}", err=True)
                raise typer.Exit(2) from exc

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError


class ConfigPublishCommand(Command):
    name: ClassVar[str] = "config:publish"
    help: ClassVar[str] = "Publish package config files into the app"
    needs_application: ClassVar[bool] = True

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
                _Option("--tag", help="Config publish tag. Defaults to tags containing 'config'."),
            ] = None,
            force: Annotated[
                bool,
                _Option("--force", help="Overwrite destination files that already exist."),
            ] = False,
        ) -> None:
            code = cmd_self._publish(provider=provider, tag=tag, force=force)
            if code != 0:
                raise typer.Exit(code)

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    def _publish(self, *, provider: str | None, tag: str | None, force: bool) -> int:
        command = VendorPublishCommand()
        command.app = self.app
        return command.publish(provider=provider, tag=tag or "config", force=force)


class ConfigCacheCommand(Command):
    name: ClassVar[str] = "config:cache"
    help: ClassVar[str] = "Serialize the loaded config registry to bootstrap/cache/config.json."
    needs_application: ClassVar[bool] = True

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback() -> None:
            dest = cmd_self.cache_path()
            count = dump_config_cache(dest)
            typer.echo(f"Config cached ({count} module(s)) → {dest}")

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    def cache_path(self) -> Path:
        if self.app is not None:
            with contextlib.suppress(AttributeError, TypeError):
                return self.app.base_path() / CONFIG_CACHE_REL
        return Path.cwd() / CONFIG_CACHE_REL


class ConfigClearCommand(Command):
    name: ClassVar[str] = "config:clear"
    help: ClassVar[str] = "Delete the cached config file so the next boot reads config/*.py."

    def register(self, app: typer.Typer) -> None:
        def _callback() -> None:
            dest = Path.cwd() / CONFIG_CACHE_REL
            if dest.exists():
                dest.unlink()
                typer.echo(f"Removed {dest}")
            else:
                typer.echo("Config cache not found — nothing to clear.")
            reset()

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError


__all__ = ["ConfigCacheCommand", "ConfigClearCommand", "ConfigPublishCommand", "ConfigShowCommand"]
