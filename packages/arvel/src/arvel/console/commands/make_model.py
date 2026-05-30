"""``make:model`` — generate a SQLAlchemy declarative Arvel model.

Arvel models extend :class:`arvel.database.Model` (which composes
SQLAlchemy :class:`DeclarativeBase` with Arvel's ``ActiveRecord``
mixin). Columns use the typed helpers in :mod:`arvel.database.columns`
(``id_``, ``string``, ``integer``, …) — each is a thin wrapper around
:func:`sqlalchemy.orm.mapped_column` that returns ``Mapped[T]``, so
pyright and mypy strict mode see the column type without any extra
annotation work. Drop down to ``mapped_column(...)`` when a column needs
something the helpers don't cover.

The default stub includes a primary key, a sample text column, and the
:class:`arvel.database.Timestamps` mixin so ``created_at`` /
``updated_at`` columns are populated by the framework. Add
:class:`arvel.database.SoftDeletes` for ``deleted_at``-style soft delete
support.

Pass ``--view`` to generate a read-only :class:`arvel.database.ViewModel`
stub, or ``--materialized-view`` for a ViewModel with
``__is_materialized_view__ = True`` and a ``refresh()`` call example.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, ClassVar

import typer

from arvel.console import Command, Context
from arvel.console._t import Argument as _Argument
from arvel.console._t import Option as _Option
from arvel.database.migrations import extract_table_name
from arvel.support.str import Str

_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

_TEMPLATE_MODEL = '''"""{title} — ORM model."""

from __future__ import annotations

from arvel.database import Model, Timestamps, id_, string
from sqlalchemy.orm import Mapped


class {title}(Model, Timestamps):
    __tablename__ = "{table}"
    __guarded__ = ["*"]

    id: Mapped[int] = id_()
    name: Mapped[str] = string(255)
'''

_TEMPLATE_VIEW = '''"""{title} — read-only view model."""

from __future__ import annotations

from arvel.database import ViewModel, id_
from sqlalchemy.orm import Mapped


class {title}(ViewModel):
    __tablename__ = "{table}"

    id: Mapped[int] = id_()
    # define columns to match your view\'s shape
'''

_TEMPLATE_MATERIALIZED_VIEW = '''"""{title} — materialized view model."""

from __future__ import annotations

from arvel.database import ViewModel, id_
from sqlalchemy.orm import Mapped


class {title}(ViewModel):
    __tablename__ = "{table}"
    __is_materialized_view__ = True

    id: Mapped[int] = id_()
    # define columns to match your view\'s shape
'''


class MakeModelCommand(Command):
    name: ClassVar[str] = "make:model"
    help: ClassVar[str] = "Generate an ORM model (arvel.database.Model)"
    _target_subdir: ClassVar[str] = "app/models"

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            name: Annotated[str, _Argument(help="Class name")],
            *,
            force: Annotated[bool, _Option("--force", help="Overwrite existing")] = False,
            view: Annotated[bool, _Option("--view", help="Generate a ViewModel stub")] = False,
            materialized_view: Annotated[
                bool,
                _Option("--materialized-view", help="Generate a materialized ViewModel stub"),
            ] = False,
        ) -> None:
            if view and materialized_view:
                typer.echo(
                    "arvel: --view and --materialized-view are mutually exclusive.", err=True
                )
                raise typer.Exit(2)
            code = cmd_self._generate(
                name, force=force, view=view, materialized_view=materialized_view
            )
            if code != 0:
                raise typer.Exit(code)

        app.command(name=self.name, help=self.help)(_callback)

    def _generate(
        self,
        name: str,
        *,
        force: bool = False,
        view: bool = False,
        materialized_view: bool = False,
    ) -> int:
        if not name or not _NAME_PATTERN.match(name):
            typer.echo(
                "arvel: Name must match ^[A-Za-z][A-Za-z0-9_]*$ "
                "(letters, digits, underscore; must start with a letter).",
                err=True,
            )
            return 2

        target = Path(self._target_subdir) / f"{Str.snake(name)}.py"
        if target.exists() and not force:
            typer.echo(f"arvel: {target} already exists. Pass --force to overwrite.", err=True)
            return 1
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._render(name, view=view, materialized_view=materialized_view))
        typer.echo(f"Created: {target}")
        return 0

    def _render(
        self,
        name: str,
        *,
        view: bool = False,
        materialized_view: bool = False,
    ) -> str:
        title = Str.pascal(name)
        table = extract_table_name(name)
        if materialized_view:
            return _TEMPLATE_MATERIALIZED_VIEW.format(title=title, table=table)
        if view:
            return _TEMPLATE_VIEW.format(title=title, table=table)
        return _TEMPLATE_MODEL.format(title=title, table=table)
