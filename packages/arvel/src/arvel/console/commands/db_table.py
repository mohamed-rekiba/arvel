"""db:table command."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Annotated, ClassVar

import typer
from sqlalchemy import inspect

from arvel.console import Command, Context
from arvel.console._subsystem import CliSubsystem
from arvel.console._t import Argument as _Argument
from arvel.console.commands.migrate import resolve_engine

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection as SyncConnection


class DbTableCommand(Command):
    name: ClassVar[str] = "db:table"
    help: ClassVar[str] = "Print columns and indexes for a table"
    requires: ClassVar[frozenset[CliSubsystem]] = frozenset(
        {CliSubsystem.DATABASE, CliSubsystem.USER_PROVIDERS}
    )

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            table: Annotated[str, _Argument(help="Table name")],
        ) -> None:
            try:
                exists = asyncio.run(cmd_self._show(table))
            except Exception as exc:
                typer.echo(f"arvel: {exc}", err=True)
                raise typer.Exit(code=2) from exc
            if not exists:
                typer.echo(f"arvel: table '{table}' does not exist.", err=True)
                raise typer.Exit(code=2)

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    async def _show(self, table: str) -> bool:
        engine = resolve_engine(self.app)
        async with engine.connect() as conn:
            details = await conn.run_sync(_collect_table_details, table)
        if details is None:
            return False
        typer.echo(f"Table: {table}")
        typer.echo("Columns:")
        for col in details["columns"]:
            nullable = "NULL" if col["nullable"] else "NOT NULL"
            typer.echo(f"  - {col['name']}: {col['type']} {nullable}")
        typer.echo("Indexes:")
        for idx in details["indexes"]:
            typer.echo(f"  - {idx['name']}: {idx['columns']}")
        return True


def _collect_table_details(sync_conn: SyncConnection, table: str) -> _TableDetails | None:
    insp = inspect(sync_conn)
    names = set(insp.get_table_names())
    if table not in names:
        return None
    columns: list[dict[str, object]] = [
        {
            "name": col["name"],
            "type": str(col["type"]),
            "nullable": bool(col.get("nullable", True)),
        }
        for col in insp.get_columns(table)
    ]
    indexes: list[dict[str, object]] = [
        {"name": idx["name"], "columns": list(idx.get("column_names") or [])}
        for idx in insp.get_indexes(table)
    ]
    return {"columns": columns, "indexes": indexes}


_TableDetails = dict[str, list[dict[str, object]]]
