"""``model:prune`` — delete stale model rows via the ``Prunable`` mixin."""

from __future__ import annotations

from typing import Any, ClassVar

import typer

from arvel.console import Command, Context
from arvel.console import _async as _arvel_async
from arvel.console._subsystem import CliSubsystem
from arvel.database.model import Model, Prunable


class ModelPruneCommand(Command):
    name: ClassVar[str] = "model:prune"
    help: ClassVar[str] = "Delete stale rows for all Prunable models."
    requires: ClassVar[frozenset[CliSubsystem]] = frozenset(
        {CliSubsystem.DATABASE, CliSubsystem.USER_PROVIDERS}
    )

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback() -> None:
            _arvel_async.schedule_async(cmd_self.prune())

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    async def prune(self) -> None:
        if self.app is None:
            typer.echo("arvel: model:prune requires a bound Application.", err=True)
            raise typer.Exit(2)

        total = 0
        for model_cls in collect_prunable_models():
            instance: Any = model_cls()
            qb = instance.prunable_query()
            # force_delete: pruning permanently removes rows, even on SoftDeletes models.
            deleted = await qb.force_delete()
            typer.echo(f"Pruned {deleted} row(s) from {model_cls.__name__}.")
            total += deleted

        typer.echo(f"Done. {total} total row(s) pruned.")


def collect_prunable_models() -> list[type[Any]]:
    """Walk Arvel's mapper registry and return concrete Prunable subclasses."""
    found: list[type[Any]] = []
    for mapper in Model.registry.mappers:
        cls = mapper.class_
        if issubclass(cls, Prunable):
            if getattr(cls, "__abstract__", False):
                continue
            found.append(cls)
    return found


__all__ = ["ModelPruneCommand"]
