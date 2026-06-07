"""migrate:reset command."""

from __future__ import annotations

from typing import ClassVar

import typer

from arvel.console import Command, Context
from arvel.console import _async as _arvel_async
from arvel.console._subsystem import CliSubsystem
from arvel.console.commands.migrate import (
    BootstrapFailedError,
    build_migrator,
)
from arvel.database.migrator import (
    MigrationFailedError,
    MigrationFileInvalidError,
)


class MigrateResetCommand(Command):
    name: ClassVar[str] = "migrate:reset"
    help: ClassVar[str] = "Roll back every applied migration in reverse order"
    requires: ClassVar[frozenset[CliSubsystem]] = frozenset({CliSubsystem.DATABASE})

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback() -> None:
            async def _run() -> None:
                try:
                    rolled = await cmd_self._run()
                except MigrationFailedError as exc:
                    typer.echo(
                        f"arvel: rollback failed: {exc.name} — "
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

                if not rolled:
                    typer.echo("Nothing to roll back.")
                    return
                typer.echo(f"Rolled back {len(rolled)} migration(s):")
                for name in rolled:
                    typer.echo(f"  - {name}")

            _arvel_async.schedule_async(_run())

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    async def _run(self) -> list[str]:
        migrator = build_migrator(self.app)
        await migrator.ensure_table()
        return await migrator.reset()
