"""auth:clear-resets command — delete expired password reset tokens."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import typer
from sqlalchemy import MetaData, Table, delete, text
from sqlalchemy import inspect as sa_inspect

from arvel.console import Command, Context
from arvel.console import _async as _arvel_async
from arvel.console._subsystem import CliSubsystem
from arvel.console.commands.migrate import resolve_engine

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection as SyncConnection


class AuthClearResetsCommand(Command):
    name: ClassVar[str] = "auth:clear-resets"
    help: ClassVar[str] = "Delete expired password_reset_tokens rows"
    requires: ClassVar[frozenset[CliSubsystem]] = frozenset(
        {CliSubsystem.AUTH}  # AUTH closure pulls in DATABASE
    )

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback() -> None:
            async def _dispatch() -> None:
                try:
                    count = await cmd_self._run()
                except _NoResetsTableError as exc:
                    typer.echo(f"arvel: {exc}", err=True)
                    raise typer.Exit(code=2) from exc
                except Exception as exc:
                    typer.echo(f"arvel: {exc}", err=True)
                    raise typer.Exit(code=2) from exc
                typer.echo(f"Deleted {count} expired reset token(s).")

            _arvel_async.schedule_async(_dispatch())

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    async def _run(self) -> int:
        engine = resolve_engine(self.app)
        async with engine.begin() as conn:
            return await conn.run_sync(_delete_expired)


class _NoResetsTableError(RuntimeError):
    """Raised when the password_reset_tokens table is absent."""


def _delete_expired(sync_conn: SyncConnection) -> int:
    insp = sa_inspect(sync_conn)
    if "password_reset_tokens" not in set(insp.get_table_names()):
        msg = "password_reset_tokens table does not exist."
        raise _NoResetsTableError(msg)
    metadata = MetaData()
    table = Table("password_reset_tokens", metadata, autoload_with=sync_conn)
    threshold = text("created_at < datetime('now', '-3600 seconds')")
    result = sync_conn.execute(delete(table).where(threshold))
    return int(result.rowcount or 0)
