"""``scout:import`` / ``scout:flush`` — bulk (re)index or empty a searchable model's index. ``MODEL`` is either a dotted ``module:ClassName`` path (the same shape
``LazyGroup``'s command manifest uses) or, inside a project, a model's bare class name resolved
from ``app/models`` (like the shell's model autoload). Grounded in doc 13-console + the
05-SEARCH-SCOUT spec.
"""

from __future__ import annotations

import importlib
from typing import Any

import typer

scout_import_app = typer.Typer()
scout_flush_app = typer.Typer()


def _resolve_model(app: Any, target: str) -> Any:
    if ":" in target:
        module_name, _, attr = target.partition(":")
        cls = getattr(importlib.import_module(module_name), attr, None)
        if cls is None:
            raise typer.BadParameter(f"{module_name!r} has no attribute {attr!r}")
        return cls
    from arvel.console.shell import defined_models, import_app_models

    import_app_models(app)  # so app/models/*.py's classes are loaded and discoverable below
    cls = defined_models().get(target)
    if cls is None:
        raise typer.BadParameter(
            f"no model named {target!r} (use a dotted 'module:ClassName' path, or a bare name "
            "defined under app/models)"
        )
    return cls


async def _require_engine(cls: Any) -> Any:
    engine = cls._search_engine()
    if engine is None:
        typer.echo("no search engine bound; configure 'search' in your app")
        raise typer.Exit(1)
    return engine


@scout_import_app.command("scout:import")
def scout_import(
    model: str = typer.Argument(..., help="dotted 'module:ClassName' path or app model name"),
) -> None:
    """Bulk-index every row of MODEL (chunked), after pushing its filterable/sortable settings."""
    from arvel.console.kernel import run_app_command

    async def _handler(app: Any) -> None:
        cls = _resolve_model(app, model)
        engine = await _require_engine(cls)
        index = cls.searchable_as()
        await engine.configure(
            index, filterable=cls.searchable_filterable(), sortable=cls.searchable_sortable()
        )

        count = 0

        async def _index_chunk(rows: list[Any]) -> None:
            nonlocal count
            for row in rows:
                await row.searchable()
            count += len(rows)
            typer.echo(f"imported {count} record(s)...")

        await cls.query().chunk_by_id(200, _index_chunk)
        typer.echo(f"scout:import complete: {count} record(s) indexed into {index!r}")

    run_app_command(_handler)


@scout_flush_app.command("scout:flush")
def scout_flush(
    model: str = typer.Argument(..., help="dotted 'module:ClassName' path or app model name"),
) -> None:
    """Empty MODEL's search index."""
    from arvel.console.kernel import run_app_command

    async def _handler(app: Any) -> None:
        cls = _resolve_model(app, model)
        await _require_engine(cls)
        await cls.remove_all_from_search()
        typer.echo(f"flushed {cls.searchable_as()!r}")

    run_app_command(_handler)
