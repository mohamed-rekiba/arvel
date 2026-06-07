"""migrate, migrate:rollback, migrate:status commands.

Exit codes follow the honest-failure rule:
- 0 — success
- 1 — migration body raised
- 2 — bootstrap failed or the database is unavailable
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, ClassVar

import typer
from sqlalchemy.ext.asyncio import AsyncEngine

from arvel.console import Command, Context
from arvel.console import _async as _arvel_async
from arvel.console._subsystem import CliSubsystem
from arvel.console._t import Option as _Option
from arvel.database.health import DatabaseUnavailableError, check_database_connection
from arvel.database.migrator import (
    MigrationFailedError,
    MigrationFileInvalidError,
    MigrationStatus,
    Migrator,
)


class BootstrapFailedError(RuntimeError):
    """Raised when the framework Application can't supply an AsyncEngine.

    Maps to exit code 2.
    """


def resolve_engine(app: object) -> AsyncEngine:
    """Pull the singleton ``AsyncEngine`` out of the container."""
    container = getattr(app, "container", None)
    if container is None:
        raise BootstrapFailedError("bootstrap failed: no container on Application")
    make = getattr(container, "make", None)
    if make is None:
        raise BootstrapFailedError("bootstrap failed: container has no .make()")
    engine = make(AsyncEngine)
    if not isinstance(engine, AsyncEngine):
        raise BootstrapFailedError("bootstrap failed: container did not return an AsyncEngine")
    return engine


def _resolve_base_path(app: object) -> Path:
    base_path = getattr(app, "base_path", None)
    if base_path is None:
        return Path.cwd()
    if callable(base_path):
        return _coerce_to_path(base_path())
    return _coerce_to_path(base_path)


def _coerce_to_path(value: object) -> Path:
    if isinstance(value, Path):
        return value
    if isinstance(value, str):
        return Path(value)
    raise TypeError(f"base_path must be a str or pathlib.Path, got {type(value).__name__}")


def _resolve_migrations_dir(app: object) -> Path:
    return _resolve_base_path(app) / "database" / "migrations"


def build_migrator(app: object) -> Migrator:
    return Migrator(resolve_engine(app), _resolve_migrations_dir(app))


class MigrateCommand(Command):
    name: ClassVar[str] = "migrate"
    help: ClassVar[str] = "Run pending database migrations"
    requires: ClassVar[frozenset[CliSubsystem]] = frozenset({CliSubsystem.DATABASE})

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            *,
            dry_run: Annotated[
                bool,
                _Option("--dry-run", help="Print migrations that would run."),
            ] = False,
        ) -> None:
            _arvel_async.schedule_async(cmd_self._exec_migrate(dry_run=dry_run))

        app.command(name=self.name, help=self.help)(_callback)

    async def _exec_migrate(self, *, dry_run: bool) -> None:
        try:
            applied = await self._run_migrations(dry_run=dry_run)
        except DatabaseUnavailableError as exc:
            typer.echo(f"arvel: database is not available — {exc}", err=True)
            raise typer.Exit(code=2) from exc
        except MigrationFailedError as exc:
            typer.echo(
                f"arvel: migration failed: {exc.name} — "
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

        if dry_run:
            _print_migrate_result(applied, mode="dry")
        else:
            _print_migrate_result(applied, mode="run")

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    async def _run_migrations(self, *, dry_run: bool = False) -> list[str]:
        engine = resolve_engine(self.app)
        await check_database_connection(engine)
        migrator = Migrator(engine, _resolve_migrations_dir(self.app))
        await migrator.ensure_table()
        return await migrator.upgrade(dry_run=dry_run)


class MigrateRollbackCommand(Command):
    name: ClassVar[str] = "migrate:rollback"
    help: ClassVar[str] = "Roll back the last batch of migrations"
    requires: ClassVar[frozenset[CliSubsystem]] = frozenset({CliSubsystem.DATABASE})

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback() -> None:
            async def _run() -> None:
                try:
                    rolled = await cmd_self._run_rollback()
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

    async def _run_rollback(self) -> list[str]:
        migrator = build_migrator(self.app)
        await migrator.ensure_table()
        return await migrator.rollback()


class MigrateStatusCommand(Command):
    name: ClassVar[str] = "migrate:status"
    help: ClassVar[str] = "Show migration status"
    requires: ClassVar[frozenset[CliSubsystem]] = frozenset({CliSubsystem.DATABASE})

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback() -> None:
            async def _run() -> None:
                try:
                    rows = await cmd_self._get_status()
                except BootstrapFailedError as exc:
                    typer.echo(f"arvel: {exc}", err=True)
                    raise typer.Exit(code=2) from exc

                _render_status_table(rows)

            _arvel_async.schedule_async(_run())

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    async def _get_status(self) -> list[MigrationStatus]:
        migrator = build_migrator(self.app)
        await migrator.ensure_table()
        return await migrator.status()


def _print_migrate_result(applied: list[str], *, mode: str) -> None:
    if not applied:
        typer.echo("Nothing to migrate.")
        return
    if mode == "dry":
        typer.echo(f"Would run {len(applied)} migration(s):")
    else:
        typer.echo(f"Ran {len(applied)} migration(s):")
    for name in applied:
        typer.echo(f"  - {name}")


def _render_status_table(rows: list[MigrationStatus]) -> None:
    """Pretty-print the status table."""
    header_name = "Migration"
    header_applied = "Applied"
    header_batch = "Batch"
    header_at = "Applied At"
    name_w = max(len(header_name), *(len(r.name) for r in rows), 30)
    typer.echo(f"{header_name:<{name_w}}  {header_applied:<8}  {header_batch:<6}  {header_at}")
    typer.echo("-" * (name_w + 8 + 6 + 19 + 6))
    for row in rows:
        applied = "Yes" if row.applied else "No"
        batch = str(row.batch) if row.batch is not None else "-"
        at = row.applied_at.strftime("%Y-%m-%d %H:%M:%S") if row.applied_at is not None else "-"
        typer.echo(f"{row.name:<{name_w}}  {applied:<8}  {batch:<6}  {at}")
