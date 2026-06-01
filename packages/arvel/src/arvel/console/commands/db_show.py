"""db:show command."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import typer
from sqlalchemy import inspect

from arvel.console import Command, Context
from arvel.console.commands.migrate import resolve_engine

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection as SyncConnection


@dataclass(frozen=True)
class DatabaseInfo:
    driver: str
    database: str
    tables: list[str]


class DbShowCommand(Command):
    name: ClassVar[str] = "db:show"
    help: ClassVar[str] = "Print database connection and table summary"
    needs_application: ClassVar[bool] = True

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback() -> None:
            try:
                asyncio.run(cmd_self._show())
            except Exception as exc:
                typer.echo(f"arvel: {exc}", err=True)
                raise typer.Exit(code=2) from exc

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    async def _show(self) -> None:
        engine = resolve_engine(self.app)
        async with engine.connect() as conn:
            info = await conn.run_sync(_collect_database_info)
        typer.echo(f"Driver:   {info.driver}")
        typer.echo(f"Database: {info.database}")
        typer.echo(f"Tables:   {len(info.tables)}")
        for name in info.tables:
            typer.echo(f"  - {name}")


def _collect_database_info(sync_conn: SyncConnection) -> DatabaseInfo:
    insp = inspect(sync_conn)
    tables: list[str] = list(insp.get_table_names())
    database = sync_conn.engine.url.database or "?"
    return DatabaseInfo(
        driver=sync_conn.dialect.name,
        database=database,
        tables=tables,
    )
