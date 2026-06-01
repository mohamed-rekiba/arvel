"""``make:model`` — generate a SQLAlchemy declarative Arvel model.

Arvel models extend :class:`arvel.database.Model` (which composes
SQLAlchemy :class:`DeclarativeBase` with Arvel's ``ActiveRecord``
mixin). Columns use the typed helpers in :mod:`arvel.database.columns`
(``id_``, ``string``, ``integer``, …). Write the plain annotation
(``id: int = id_()``); the model metaclass wraps it in ``Mapped[int]`` at
runtime. Relationships are plain too — ``posts: list[Post] = relationship(...)``
— and a bare annotation (``name: str``) with no helper infers its column.
You never write the SQLAlchemy wrapper yourself.

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
from arvel.console.commands import _companions
from arvel.database.migrations import extract_table_name
from arvel.support.str import Str

_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

_TEMPLATE_MODEL = '''"""{title} — ORM model."""

from __future__ import annotations

from arvel.database import Model, Timestamps, id_, string


class {title}(Model, Timestamps):
    __tablename__ = "{table}"
    __guarded__ = ["*"]

    id: int = id_()
    name: str = string(255)
'''

_TEMPLATE_VIEW = '''"""{title} — read-only view model."""

from __future__ import annotations

from arvel.database import ViewModel, id_


class {title}(ViewModel):
    __tablename__ = "{table}"

    id: int = id_()
    # define columns to match your view\'s shape
'''

_TEMPLATE_MATERIALIZED_VIEW = '''"""{title} — materialized view model."""

from __future__ import annotations

from arvel.database import ViewModel, id_


class {title}(ViewModel):
    __tablename__ = "{table}"
    __is_materialized_view__ = True

    id: int = id_()
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
            name: Annotated[str, _Argument(help="Model name (e.g. Post)")],
            *,
            force: Annotated[bool, _Option("--force", help="Overwrite existing")] = False,
            view: Annotated[bool, _Option("--view", help="Generate a ViewModel stub")] = False,
            materialized_view: Annotated[
                bool,
                _Option("--materialized-view", help="Generate a materialized ViewModel stub"),
            ] = False,
            migration: Annotated[
                bool, _Option("--migration", "-m", help="Also create a migration")
            ] = False,
            factory: Annotated[
                bool, _Option("--factory", "-f", help="Also create a factory")
            ] = False,
            seed: Annotated[bool, _Option("--seed", "-s", help="Also create a seeder")] = False,
            controller: Annotated[
                bool, _Option("--controller", "-c", help="Also create a controller")
            ] = False,
            resource: Annotated[
                bool, _Option("--resource", help="Make the companion controller a resource")
            ] = False,
            api: Annotated[
                bool, _Option("--api", help="API resource controller (requires --controller)")
            ] = False,
            requests: Annotated[
                bool, _Option("--requests", help="Also create Store/Update FormRequests")
            ] = False,
            policy: Annotated[bool, _Option("--policy", "-p", help="Also create a policy")] = False,
            observer: Annotated[
                bool, _Option("--observer", "-o", help="Also create an observer")
            ] = False,
            json_resource: Annotated[
                bool, _Option("--json-resource", "-R", help="Also create a JsonResource")
            ] = False,
            test: Annotated[bool, _Option("--test", help="Also create a feature test")] = False,
            all_: Annotated[
                bool, _Option("--all", "-a", help="Create model + every companion")
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

            # View models are read-only projections — companions don't apply.
            if view or materialized_view:
                return

            if all_:
                migration = factory = seed = controller = True
                requests = policy = observer = json_resource = test = True
                resource = True

            if api and not controller:
                typer.echo("arvel: --api requires --controller.", err=True)
                raise typer.Exit(2)

            root = Str.pascal(name)
            if migration:
                code = _companions.migration(root) or code
            if factory:
                code = _companions.factory(root, force=force) or code
            if seed:
                code = _companions.seeder(root, force=force) or code
            if policy:
                code = _companions.policy(root, force=force) or code
            if observer:
                code = _companions.observer(root, force=force) or code
            if json_resource:
                code = _companions.json_resource(root, force=force) or code
            if requests:
                code = _companions.form_requests(root, force=force) or code
            if controller:
                code = (
                    _companions.controller(
                        root, force=force, resource=resource, api=api, model_root=root
                    )
                    or code
                )
            if test:
                code = _companions.feature_test(root, force=force) or code
            if code != 0:
                raise typer.Exit(code)

        app.command(name=self.name, help=self.help)(_callback)

    def _generate(
        self,
        name: str,
        *,
        force: bool = False,
        exist_ok: bool = False,
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
            if exist_ok:
                typer.echo(f"Exists: {target}")
                return 0
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
