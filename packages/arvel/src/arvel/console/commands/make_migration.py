"""``make:migration`` — generate a timestamped Arvel-shaped migration stub.

The generator writes ``database/migrations/<timestamp>_<snake_name>.py`` with
a :class:`arvel.database.Migration` subclass that exposes
``async def up(self)`` / ``async def down(self)`` and references the standard
:class:`arvel.database.Blueprint` / :class:`arvel.database.Schema`
primitives, so the user can start defining columns immediately.

The migration class name mirrors the input verbatim (``CreateUsersTable``);
the table name is extracted by stripping common verb prefixes
(``Create``/``Add``/``Drop``/``Alter``/``Update``) and the ``Table`` suffix
(``CreateUsersTable`` → ``users``).

When two invocations land in the same second, the second gets a microsecond
suffix so back-to-back generations don't collide.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Annotated, ClassVar

import typer

from arvel.console import Command, Context
from arvel.console._t import Argument as _Argument
from arvel.console._t import Option as _Option
from arvel.database.migrations import (
    extract_extension_name,
    extract_table_name,
    extract_view_name,
)
from arvel.support.str import Str

_TEMPLATE = '''"""{title} — schema migration."""

from __future__ import annotations

from arvel.database import Blueprint, IdType, Schema


__tablename__ = "{table_name}"

async def up(schema: Schema) -> None:
    """Apply the migration."""

    def _table(t: Blueprint) -> None:
        t.id(id_type=IdType.INT)
        t.timestamps()

    schema.create(__tablename__, _table)

async def down(schema: Schema) -> None:
    """Roll back the migration."""
    schema.drop_if_exists(__tablename__)
'''

_VIEW_TEMPLATE = '''"""{title} — view migration."""

from __future__ import annotations

from arvel.database import Schema


__viewname__ = "{view_name}"

async def up(schema: Schema) -> None:
    """Apply the migration."""
    schema.create_view(__viewname__, "SELECT 1")  # TODO: replace with your SELECT statement

async def down(schema: Schema) -> None:
    """Roll back the migration."""
    schema.drop_view_if_exists(__viewname__)
'''

_MATERIALIZED_VIEW_TEMPLATE = '''"""{title} — materialized view migration."""

from __future__ import annotations

from arvel.database import Schema


__viewname__ = "{view_name}"

async def up(schema: Schema) -> None:
    """Apply the migration."""
    # TODO: replace SELECT with your query
    schema.create_materialized_view(__viewname__, "SELECT 1")
    # schema.refresh_materialized_view(__viewname__, concurrently=True)

async def down(schema: Schema) -> None:
    """Roll back the migration."""
    schema.drop_materialized_view_if_exists(__viewname__)
'''

_EXTENSION_TEMPLATE = '''"""{title} — extension migration."""

from __future__ import annotations

from arvel.database import Schema


# Update this if the extension name differs from the inferred value
# (e.g. "uuid-ossp" uses a hyphen — replace underscores as needed).
__extension__ = "{extension_name}"

async def up(schema: Schema) -> None:
    """Apply the migration."""
    schema.install_extension(__extension__)

async def down(schema: Schema) -> None:
    """Roll back the migration."""
    schema.uninstall_extension(__extension__)
'''

_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


def _validate_name(name: str) -> str | None:
    """Return None when ``name`` is safe to embed in a filename and docstring."""
    if not name:
        return "Migration name must not be empty."
    if not _NAME_PATTERN.match(name):
        return (
            "Migration name must match ^[A-Za-z][A-Za-z0-9_]*$ "
            "(letters, digits, underscore; must start with a letter)."
        )
    return None


class MakeMigrationCommand(Command):
    name: ClassVar[str] = "make:migration"
    help: ClassVar[str] = "Create a new migration file under database/migrations/"

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            name: Annotated[str, _Argument(help="Migration name (e.g. CreateUsersTable)")],
            *,
            view: Annotated[
                bool,
                _Option("--view", help="Scaffold a view migration instead of a table"),
            ] = False,
            materialized_view: Annotated[
                bool,
                _Option(
                    "--materialized-view",
                    help="Scaffold a materialized view migration (PostgreSQL only)",
                ),
            ] = False,
            extension: Annotated[
                bool,
                _Option("--extension", help="Scaffold an extension install migration"),
            ] = False,
        ) -> None:
            code = cmd_self.make(
                name, view=view, materialized_view=materialized_view, extension=extension
            )
            if code != 0:
                raise typer.Exit(code)

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    def make(
        self,
        name: str,
        *,
        view: bool = False,
        materialized_view: bool = False,
        extension: bool = False,
    ) -> int:
        scaffold_flags = int(view) + int(materialized_view) + int(extension)
        if scaffold_flags > 1:
            typer.echo(
                "ERROR: --view, --materialized-view, and --extension are mutually exclusive.",
                err=True,
            )
            return 2

        error = _validate_name(name)
        if error is not None:
            typer.echo(f"ERROR: {error}", err=True)
            return 2

        target_dir = Path("database") / "migrations"
        target_dir.mkdir(parents=True, exist_ok=True)

        file_stem = Str.snake(name)

        timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y_%m_%d_%H%M%S")
        candidate = target_dir / f"{timestamp}_{file_stem}.py"
        if candidate.exists():
            ts_micro = datetime.datetime.now(datetime.UTC).strftime("%Y_%m_%d_%H%M%S_%f")
            candidate = target_dir / f"{ts_micro}_{file_stem}.py"

        if view:
            content = _VIEW_TEMPLATE.format(
                title=Str.pascal(name),
                view_name=extract_view_name(file_stem),
            )
        elif materialized_view:
            content = _MATERIALIZED_VIEW_TEMPLATE.format(
                title=Str.pascal(name),
                view_name=extract_view_name(file_stem),
            )
        elif extension:
            content = _EXTENSION_TEMPLATE.format(
                title=Str.pascal(name),
                extension_name=extract_extension_name(name),
            )
        else:
            content = _TEMPLATE.format(
                title=Str.pascal(name),
                table_name=extract_table_name(file_stem),
            )

        candidate.write_text(content)
        typer.echo(f"Migration created: {candidate}")
        return 0


__all__ = ["MakeMigrationCommand"]
