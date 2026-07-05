"""``feature:list`` / ``feature:purge``. Both boot the app so any
``Feature.define(...)`` calls made in a provider's ``boot()`` have already run."""

from __future__ import annotations

from typing import Any

import typer

feature_list_app = typer.Typer()


@feature_list_app.command("feature:list")
def feature_list() -> None:
    """List every defined feature flag."""
    from arvel.console.kernel import run_app_command

    async def _handler(app: Any) -> None:
        names = app.make("features").defined()
        if not names:
            typer.echo("no features defined")
            return
        for name in names:
            typer.echo(name)

    run_app_command(_handler)


feature_purge_app = typer.Typer()


@feature_purge_app.command("feature:purge")
def feature_purge(
    name: str = typer.Argument(..., help="the feature flag name to purge"),
) -> None:
    """Clear every stored value for NAME (forces its resolver to run again for every scope)."""
    from arvel.console.kernel import run_app_command

    async def _handler(app: Any) -> None:
        await app.make("features").purge(name)
        typer.echo(f"purged {name!r}")

    run_app_command(_handler)
