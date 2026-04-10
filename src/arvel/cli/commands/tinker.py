"""Interactive REPL with pre-loaded application context.

Bootstraps the Arvel application and drops into an interactive Python shell
with ``app``, ``container``, ``session``, and auto-discovered models in the
namespace. Uses IPython when available, falls back to the standard
``code.interact``.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import inspect
import os
import pkgutil
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import typer

from arvel.logging import Log

tinker_app = typer.Typer(name="tinker", help="Interactive REPL with application context.")

logger = Log.named("arvel.cli.tinker")


def _discover_models(base_path: Path) -> dict[str, type]:
    """Auto-discover ArvelModel subclasses from ``app/models/``."""
    from arvel.data.model import ArvelModel

    models: dict[str, type] = {}
    models_path = base_path / "app" / "models"
    if not models_path.is_dir():
        return models

    package_name = "app.models"
    for _finder, module_name, _is_pkg in pkgutil.iter_modules([str(models_path)]):
        if module_name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"{package_name}.{module_name}")
        except Exception:
            logger.debug("tinker_model_import_failed", module=module_name)
            continue
        for name, obj in inspect.getmembers(mod, inspect.isclass):
            if issubclass(obj, ArvelModel) and obj is not ArvelModel:
                models[name] = obj

    return models


def _build_namespace() -> dict[str, Any]:
    """Bootstrap the Arvel application and build the REPL namespace."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from arvel.foundation.application import Application

    application = asyncio.run(Application.create())

    session: AsyncSession | None = None
    with contextlib.suppress(Exception):
        session = asyncio.run(application.container.resolve(AsyncSession))

    ns: dict[str, Any] = {
        "app": application,
        "container": application.container,
        "config": application.config,
        "session": session,
    }

    models = _discover_models(application.base_path)
    ns.update(models)

    return ns


def _start_repl(namespace: dict[str, Any]) -> None:
    """Launch IPython (preferred) or stdlib ``code.interact``."""
    try:
        from IPython import (
            start_ipython,  # type: ignore[import-untyped]
        )

        start_ipython(argv=[], user_ns=namespace)
    except ImportError, TypeError:
        import code

        code.interact(local=namespace, banner="Arvel Tinker (stdlib)")


def _shutdown(namespace: dict[str, Any]) -> None:
    """Clean up resources — close DB connections, dispose engine, etc."""
    session = namespace.get("session")
    if session is not None and hasattr(session, "close"):
        with contextlib.suppress(Exception):
            asyncio.run(session.close())

    application = namespace.get("app")
    if application is not None and hasattr(application, "shutdown"):
        asyncio.run(application.shutdown())


@tinker_app.callback(invoke_without_command=True)
def tinker(
    ctx: typer.Context,
    execute: str | None = typer.Option(
        None,
        "--execute",
        "-e",
        help="Evaluate expression and print result.",
    ),
    force: bool = typer.Option(False, "--force", help="Allow running in production."),
) -> None:
    """Start an interactive REPL with the application context pre-loaded."""
    if ctx.invoked_subcommand is not None:
        return

    app_env = os.environ.get("APP_ENV", "development")

    if app_env == "production" and not force:
        typer.echo("Error: tinker is disabled in production. Use --force to override.")
        raise typer.Exit(code=1)

    if execute is not None:
        result = eval(execute)  # noqa: S307
        typer.echo(repr(result))
        return

    namespace = _build_namespace()
    try:
        _start_repl(namespace)
    finally:
        _shutdown(namespace)
