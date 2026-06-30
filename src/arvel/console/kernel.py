"""The console application kernel — boots the project's app around an app-dependent command.

Mirrors the HTTP serve path (``Application.as_asgi``) for the CLI: load the project's app from
``bootstrap/app.py`` (a ``create_app()`` factory), run the synchronous bootstrap + async ``boot()``,
run the command, then ``terminate()`` — all in **one** event loop so loop-bound resources (DB pools,
the queue broker) are created and disposed on the same loop. A spinner covers the boot while imports
and provider boot run. This is the CLI twin of B1/CLI-1. Grounded in knowledge/port/13-console.md.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

#: A command handler: ``async def handler(app) -> None``. The kernel runs it inside the booted app.
CommandHandler = Callable[[Any], Coroutine[Any, Any, None]]


def load_project_app() -> Any | None:
    """Load the project's ``Application`` from ``bootstrap/app.py`` via its ``create_app()`` factory.

    Returns ``None`` when there's no ``bootstrap/app.py`` (not inside a project) or it exposes no
    ``create_app`` — the caller turns that into a clear "run inside a project" error. The file is
    executed as Python (trusted project tree), like config files.
    """
    import importlib.util
    import sys

    cwd = Path.cwd()
    path = cwd / "bootstrap" / "app.py"
    if not path.is_file():
        return None
    # Put the project root on sys.path so bootstrap/app.py can import the app's packages (app/,
    # config/, …). `python -m arvel.console` adds cwd automatically, but the `arvel` entry-point
    # script does not — without this, `from app.providers... import ...` would fail under `arvel`.
    if (cwd_str := str(cwd)) not in sys.path:
        sys.path.insert(0, cwd_str)
    spec = importlib.util.spec_from_file_location("_arvel_bootstrap_app", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    factory = getattr(module, "create_app", None)
    return factory() if callable(factory) else None


def run_app_command(handler: CommandHandler) -> None:
    """Run an app-dependent console command inside the project app.

    If an application is **already active** (``has_application()`` — e.g. a test or an embedding host
    set it up), the handler runs against that app and its lifecycle stays the caller's to manage.
    Otherwise (the normal CLI process) the project app is loaded from ``bootstrap/app.py`` and run
    through the full single-loop lifecycle: synchronous ``bootstrap_app`` (config, providers, routes) +
    async ``boot()`` — under a spinner — then ``await handler(app)``, then ``terminate()`` even if boot
    or the handler raises. Exits 1 with a clear message when there's no active app and no project.
    """
    import asyncio

    import typer

    from arvel.kernel import app as active_app
    from arvel.kernel import has_application

    if has_application():  # tests / embedding own the app's lifecycle — just run the command
        asyncio.run(handler(active_app()))
        return
    project = load_project_app()
    if project is None:
        typer.echo("not inside an arvel project (no bootstrap/app.py with a create_app() factory)")
        raise typer.Exit(1)
    try:
        asyncio.run(_lifecycle(project, handler))
    except typer.Exit:
        raise
    except Exception as exc:  # a command failure → one concise line, not a wall of traceback
        import os

        if os.environ.get("ARVEL_DEBUG"):
            raise  # opt back into the full traceback for debugging
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        typer.secho(
            "  (set ARVEL_DEBUG=1 for the full traceback)", fg=typer.colors.BRIGHT_BLACK, err=True
        )
        raise typer.Exit(1) from exc


def load_console_routes(app: Any) -> None:
    """Load the project's ``routes/console.py`` (the file wired as the ``console`` routing entry) so its
    scheduled tasks (``Schedule.command(...).daily()`` etc.) and console definitions register against the
    booted app. CLI-only — the HTTP serve path never loads it. Loaded once per CLI invocation (each
    command is a fresh process); no console file (or none configured) is a clean no-op."""
    import importlib.util
    from pathlib import Path

    raw = getattr(app, "routing", {}).get("console")
    if not raw:
        return
    path = Path(raw)
    if not path.is_file():
        return
    spec = importlib.util.spec_from_file_location("_arvel_console_routes", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        return
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)


async def _lifecycle(app: Any, handler: CommandHandler) -> None:
    from arvel.console.spinner import Spinner
    from arvel.kernel.bootstrap import bootstrap_app, safe_terminate

    try:
        with Spinner("booting"):
            bootstrap_app(app)  # sync: env, config, providers register, routes
            await app.boot()  # async provider boot
            load_console_routes(app)  # register routes/console.py defs (scheduled tasks, commands)
    except BaseException:
        await safe_terminate(app)  # M7: a failed boot still releases half-opened resources
        raise
    try:
        await handler(app)
    finally:
        await safe_terminate(app)  # always release resources (pools, etc.), best-effort


def command_name(cls: Any) -> str:
    """The CLI name of an app/provider command class: the first token of its ``signature``
    (e.g. ``"report:send {user}"`` → ``report:send``), else the snake-cased class name."""
    signature = (getattr(cls, "signature", "") or "").strip()
    if signature:
        return signature.split()[0]
    from arvel.support import Str

    return Str.snake(cls.__name__)


_command_table: dict[str, Any] | None = None


def discover_app_commands() -> dict[str, Any]:
    """Collect the project's registered command classes as ``{name: cls}`` (CLI-3).

    Provider/app ``commands()`` populate ``app.command_classes`` during the synchronous bootstrap, so
    we load a throwaway project app, run ``bootstrap_app`` (register only — no async boot), read the
    table, then **clear** the global application so a subsequent dispatch boots a clean app through the
    normal lifecycle. Cached per process; best-effort (a broken project app yields no dynamic commands
    rather than breaking ``--help``)."""
    global _command_table
    if _command_table is not None:
        return _command_table
    import contextlib

    from arvel.kernel import set_application
    from arvel.kernel.bootstrap import bootstrap_app

    table: dict[str, Any] = {}
    try:
        # The ENTIRE discovery is best-effort: load_project_app() runs create_app() (which registers
        # the app's providers → command_classes) and bootstrap_app() discovers package providers too.
        # A broken project (e.g. a typo'd import in a command module) must NOT crash `--help`, so the
        # suppress wraps load + bootstrap (command_classes is populated by create_app, before bootstrap).
        with contextlib.suppress(Exception):
            app = load_project_app()
            if app is not None:
                bootstrap_app(app)
                table = {command_name(cls): cls for cls in app.command_classes}
                # routes/console.py's `Console.command(...)` closures populate app.console_commands;
                # load it here too so closures appear in `--help` (dispatch reloads it on its own app).
                load_console_routes(app)
                table.update(app.console_commands)  # name -> ClosureCommand
    finally:
        set_application(None)  # never leak the discovery app — dispatch boots its own clean app
    _command_table = table
    return table


def run_command_class(cls: Any) -> None:
    """Dispatch an app/provider command class through the full booted lifecycle: instantiate it and
    run ``handle`` with container dependency injection."""
    import inspect

    async def handler(app: Any) -> None:
        instance = cls()
        result = app.call((instance, "handle"))
        if inspect.isawaitable(result):
            await result

    run_app_command(handler)
