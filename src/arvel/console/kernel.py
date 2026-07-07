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
from typing import Any, cast

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
    # `python -m arvel.console` adds cwd to sys.path automatically; the `arvel` entry-point script
    # doesn't, so `from app.providers... import ...` would fail without this
    if (cwd_str := str(cwd)) not in sys.path:
        sys.path.insert(0, cwd_str)
    spec = importlib.util.spec_from_file_location("_arvel_bootstrap_app", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    factory = getattr(module, "create_app", None)
    return factory() if callable(factory) else None


def _run_to_completion(coro: Any) -> None:
    """Drive ``coro`` to completion whether or not a loop is already running. ``Cli.call`` is a
    sync API documented as callable from a request/scheduled task (i.e. from inside a running loop),
    where ``asyncio.run`` raises; there we run it on a fresh loop in a worker thread (a fresh loop
    gets its own per-loop DB connections via the resolver, so there's no cross-loop affinity bug)."""
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro)  # no loop here — the normal CLI/sync path
        return
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(asyncio.run, coro).result()


async def run_app_command_async(handler: CommandHandler) -> None:
    """Run ``handler`` against the **already-active** application, awaited directly on the
    caller's own event loop — no thread bridge (contrast :func:`_run_to_completion`, which spins a
    fresh loop in a worker thread because its callers are synchronous). For a caller that's
    already async and already has an app up (e.g. a scheduler tick, which always runs inside the
    booted app's own loop) — awaiting this directly means a slow command never blocks that loop
    for its whole duration, unlike routing through the sync :func:`run_app_command`.

    This is also ``run_app_command``'s own "already active" branch (extracted so both callers
    share one implementation); raises if no application is active — there's no project to
    (re)bootstrap here, unlike the CLI-process path in :func:`run_app_command`.
    """
    from arvel.kernel import app as active_app
    from arvel.kernel import has_application

    if not has_application():
        raise RuntimeError(
            "run_app_command_async requires an already-active application "
            "(e.g. called from a scheduler tick or another already-booted context)"
        )
    await handler(active_app())


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

    from arvel.kernel import has_application

    if has_application():  # tests / embedding own the app's lifecycle — just run the command
        _run_to_completion(run_app_command_async(handler))
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
        await safe_terminate(app)  # a failed boot still releases half-opened resources
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
        # best-effort: a broken project (e.g. a typo'd import in a command module) must not crash --help
        with contextlib.suppress(Exception):
            app = load_project_app()
            if app is not None:
                bootstrap_app(app)
                table = {command_name(cls): cls for cls in app.command_classes}
                # so routes/console.py's Console.command(...) closures also appear in --help
                load_console_routes(app)
                table.update(app.console_commands)  # name -> ClosureCommand
    finally:
        set_application(None)  # never leak the discovery app — dispatch boots its own clean app
    _command_table = table
    return table


def run_command_class(cls: Any, **cli_kwargs: Any) -> None:
    """Dispatch an app/provider command class through the full booted lifecycle: instantiate it,
    stash the parsed CLI tokens on it (so ``argument()``/``option()`` resolve — CLI-4), and run
    ``handle`` with container dependency injection."""
    import inspect

    async def handler(app: Any) -> None:
        import typer

        instance = cls()
        instance.bind_parsed(cli_kwargs)
        result = app.call((instance, "handle"))
        if inspect.isawaitable(result):
            result = await result
        # a returned int is the exit code, like a process's return status
        if isinstance(result, int) and result != 0:
            raise typer.Exit(code=result)

    run_app_command(handler)


async def run_command_class_async(cls: Any, **cli_kwargs: Any) -> None:
    """Async twin of :func:`run_command_class` — for a caller already inside the app's own event
    loop (e.g. a scheduler tick dispatching a zero-arg command) with no CLI argv to parse.
    Dispatches straight through :func:`run_app_command_async` instead of bridging through a
    thread."""
    import inspect

    async def handler(app: Any) -> None:
        import typer

        instance = cls()
        instance.bind_parsed(cli_kwargs)
        result = app.call((instance, "handle"))
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, int) and result != 0:
            raise typer.Exit(code=result)

    await run_app_command_async(handler)


class Cli:
    """Programmatic command invocation — dispatches in
    process and returns the exit code.

    Built-in framework commands (``about``, ``migrate``, ``make:*``, …) dispatch through the same
    click command the CLI uses, so ``args`` is CLI-shaped (a ``dict`` of ``{"--flag": True, "name":
    "value"}`` — see :func:`_cli_argv` — or a raw ``list[str]`` of argv tokens). App-registered
    command classes/closures (``routes/console.py`` ``Console.command(...)``, or a provider's
    ``commands()``) dispatch **directly against the already-active application** — call ``Cli``
    from inside a booted app (a request, another command, a scheduled task, or a test that set one
    up via ``set_application``), not as a bare script; there's no project to (re)boot here."""

    @staticmethod
    def call(name: str, args: dict[str, Any] | list[str] | None = None) -> int:
        return _cli_dispatch(name, args)

    @staticmethod
    def call_silently(name: str, args: dict[str, Any] | list[str] | None = None) -> int:
        """Like :meth:`call`, with stdout/stderr swallowed for the duration."""
        import contextlib
        import io

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return _cli_dispatch(name, args)


def _cli_argv(args: dict[str, Any] | list[str] | None) -> list[str]:
    """CLI-shaped ``args`` → argv tokens for a built-in (click) command. A ``--opt`` key with a
    ``True``/``False`` value is a flag (present/absent); a ``list`` value repeats the option (``{--opt=*}``
    or a variadic positional); anything else is a single value."""
    if args is None:
        return []
    if isinstance(args, list):
        return [str(a) for a in args]
    argv: list[str] = []
    for key, value in args.items():
        if key.startswith("--"):
            if value is False or value is None:
                continue
            if value is True:
                argv.append(key)
            elif isinstance(value, list):
                for item in cast("list[Any]", value):
                    argv.extend([key, str(item)])
            else:
                argv.extend([key, str(value)])
        elif isinstance(value, list):
            argv.extend(str(item) for item in cast("list[Any]", value))
        else:
            argv.append(str(value))
    return argv


def _dispatch_builtin(name: str, args: dict[str, Any] | list[str] | None) -> int:
    import importlib

    import typer

    from arvel.console.lazy import LazyGroup

    module_name, attr = LazyGroup.commands_manifest[name].split(":")
    sub_app = getattr(importlib.import_module(module_name), attr)
    command = typer.main.get_command(sub_app)
    try:
        result = command.main(args=_cli_argv(args), prog_name=name, standalone_mode=False)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    except Exception as exc:  # click UsageError/ClickException etc. carry `.exit_code`
        code = getattr(exc, "exit_code", 1)
        return code if isinstance(code, int) else 1
    return result if isinstance(result, int) else 0


def _run_and_capture_exit(fn: Any) -> int:
    import typer

    try:
        fn()
    except typer.Exit as exc:
        return exc.exit_code
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    return 0


def _cli_dispatch(name: str, args: dict[str, Any] | list[str] | None) -> int:
    from arvel.console.lazy import LazyGroup

    if name in LazyGroup.commands_manifest:
        return _dispatch_builtin(name, args)

    from arvel.kernel import app as active_app
    from arvel.kernel import has_application

    if not has_application():
        message = (
            f"Cli.call({name!r}): no active application — app-registered commands dispatch "
            "against the currently booted app (call from inside a request, another command, or a "
            "test that set one up), not as a bare script"
        )
        raise RuntimeError(message)
    if args is not None and not isinstance(args, dict):
        message = f"Cli.call({name!r}): an app-registered command takes a dict of args, not a list"
        raise TypeError(message)
    # bare param/token names (``run_closure_command``/``bind_parsed`` key on those) — a leading
    # ``--`` is accepted and stripped.
    values: dict[str, Any] = {k.removeprefix("--"): v for k, v in (args or {}).items()}

    application = active_app()
    closure = application.console_commands.get(name)
    if closure is not None:
        from arvel.console.closure import run_closure_command

        return _run_and_capture_exit(lambda: run_closure_command(name, values))
    cls = next((c for c in application.command_classes if command_name(c) == name), None)
    if cls is not None:
        return _run_and_capture_exit(lambda: run_command_class(cls, **values))
    raise ValueError(f"command {name!r} is not defined")
