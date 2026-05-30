"""cache:clear and cache:forget CLI commands.

The clear/forget callbacks deliberately let any failure propagate. The bare
``except`` swallows that lived here before WI-021 made the commands report
``Cache cleared.`` even when the cache facade was unbound — violating
NFR-021-04 (CLI exit-code honesty). If the cache subsystem is not registered,
the command surfaces ``RuntimeError("cache subsystem not registered")`` so the
exit code matches reality.

The cache table migration ships as a publishable stub on
``CacheServiceProvider``. Apps install it with
``arvel vendor:publish --tag=arvel-cache``.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from arvel.console import Command, Context
from arvel.console._t import Argument as _Argument
from arvel.console._t import Option as _Option


class CacheClearCommand(Command):
    name = "cache:clear"
    help = "Flush all items from the cache"

    def register(self, app: typer.Typer) -> None:
        def _callback(
            store: Annotated[str, _Option("--store", "-s", help="Named store to clear")] = "",
        ) -> None:
            asyncio.run(clear(store or None))

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError


class CacheForgetCommand(Command):
    name = "cache:forget"
    help = "Remove a specific key from the cache"

    def register(self, app: typer.Typer) -> None:
        def _callback(
            key: Annotated[str, _Argument(help="Cache key to remove")],
            store: Annotated[str, _Option("--store", "-s", help="Named store")] = "",
        ) -> None:
            asyncio.run(forget(key, store or None))

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError


async def clear(store_name: str | None) -> None:
    try:
        from arvel.facades.cache import Cache

        store = Cache.store(store_name)
    except Exception as exc:
        msg = "cache subsystem not registered (no CacheServiceProvider booted)"
        raise RuntimeError(msg) from exc
    await store.flush()
    typer.echo("Cache cleared.")


async def forget(key: str, store_name: str | None) -> None:
    try:
        from arvel.facades.cache import Cache

        store = Cache.store(store_name)
    except Exception as exc:
        msg = "cache subsystem not registered (no CacheServiceProvider booted)"
        raise RuntimeError(msg) from exc
    await store.forget(key)
    typer.echo(f"Removed '{key}' from cache.")
