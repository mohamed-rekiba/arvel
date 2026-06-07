"""migrate:refresh command."""

from __future__ import annotations

from typing import Annotated, ClassVar

import typer

from arvel.console import Command, Context
from arvel.console import _async as _arvel_async
from arvel.console._subsystem import CliSubsystem
from arvel.console._t import Option as _Option
from arvel.console.commands.migrate import (
    BootstrapFailedError,
    build_migrator,
)
from arvel.console.commands.migrate_fresh import invoke_db_seed
from arvel.database.migrator import (
    MigrationFailedError,
    MigrationFileInvalidError,
)
from arvel.support.env import env


def _is_production_blocked() -> bool:
    if env("ARVEL_ALLOW_DESTRUCTIVE") == "1":
        return False
    from arvel.config import config  # noqa: PLC0415

    return config("app.is_production", default=False)


class MigrateRefreshCommand(Command):
    name: ClassVar[str] = "migrate:refresh"
    help: ClassVar[str] = "Roll back every migration, then re-run them"
    requires: ClassVar[frozenset[CliSubsystem]] = frozenset(
        {CliSubsystem.DATABASE, CliSubsystem.USER_PROVIDERS}
    )

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            *,
            seed: Annotated[bool, _Option("--seed", help="Run db:seed after refreshing")] = False,
            seeder: Annotated[
                str,
                _Option("--seeder", help="Specific seeder class to run"),
            ] = "",
        ) -> None:
            if _is_production_blocked():
                typer.echo(
                    "arvel migrate:refresh refuses to drop tables in production. "
                    "Set ARVEL_ALLOW_DESTRUCTIVE=1 if you're sure.",
                    err=True,
                )
                raise typer.Exit(code=2)

            async def _run() -> None:
                try:
                    applied = await cmd_self._run(seed=seed, seeder=seeder or None)
                except MigrationFailedError as exc:
                    typer.echo(
                        f"arvel: refresh failed: {exc.name} — "
                        f"{type(exc.original).__name__}: {exc.original}",
                        err=True,
                    )
                    raise typer.Exit(code=1) from exc
                except MigrationFileInvalidError as exc:
                    typer.echo(f"arvel: {exc}", err=True)
                    raise typer.Exit(code=1) from exc
                except BootstrapFailedError as exc:
                    typer.echo(f"arvel: {exc}", err=True)
                    raise typer.Exit(code=2) from exc

                if not applied:
                    typer.echo("Nothing to refresh.")
                else:
                    typer.echo(f"Refreshed {len(applied)} migration(s):")
                    for name in applied:
                        typer.echo(f"  - {name}")

            _arvel_async.schedule_async(_run())

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    async def _run(self, *, seed: bool, seeder: str | None) -> list[str]:
        migrator = build_migrator(self.app)
        await migrator.ensure_table()
        await migrator.reset()
        applied = await migrator.upgrade()
        if seed or seeder:
            await invoke_db_seed(seeder, app=self.app)
        return applied
