"""``serve`` — run the project's ASGI app under uvicorn.

Mirrors Laravel's ``artisan serve``. Defaults to ``127.0.0.1:8000`` against the
canonical ``public.asgi:asgi`` entry point that ``arvel new`` scaffolds. Refuses
to run outside an Arvel project so users don't get a confusing ``ModuleNotFoundError``
from uvicorn looking for ``public.asgi``.
"""

from __future__ import annotations

import os
import sys
from typing import Annotated, ClassVar

import typer
import uvicorn

from arvel.console import Command, Context
from arvel.console._t import Option as _Option
from arvel.console.bootstrap import find_project_root


def _make_app_importable() -> None:
    """Put the project root on sys.path + PYTHONPATH so `public.asgi` resolves.

    `uvicorn.run()` — unlike the `uvicorn` CLI's `--app-dir .` — never adds the
    project dir to sys.path, so `import public` only works when the project is
    pip-installed. Kits aren't packages, so we add the dir holding bootstrap/app.py
    ourselves. PYTHONPATH too: --reload/--workers load the app in a spawned
    subprocess that won't inherit our in-process sys.path.
    """
    root = find_project_root()
    if root is None:
        return
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    existing = [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
    if root_str not in existing:
        os.environ["PYTHONPATH"] = os.pathsep.join([root_str, *existing])


def _graceful_shutdown_timeout() -> int | None:
    """Read GRACEFUL_SHUTDOWN_TIMEOUT (seconds). None = uvicorn's default."""
    raw = os.environ.get("GRACEFUL_SHUTDOWN_TIMEOUT", "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


class ServeCommand(Command):
    name: ClassVar[str] = "serve"
    help: ClassVar[str] = "Run the project ASGI app under uvicorn (defaults to public.asgi:asgi)"
    # uvicorn owns the event loop (and, with --reload/--workers, subprocess
    # supervisors), so serve must run outside the entrypoint's asyncio.run.
    owns_process: ClassVar[bool] = True

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            host: Annotated[str, _Option("--host", help="Interface to bind to")] = "127.0.0.1",
            port: Annotated[int, _Option("--port", help="TCP port to listen on")] = 8000,
            workers: Annotated[
                int | None, _Option("--workers", help="Number of worker processes")
            ] = None,
            *,
            reload: Annotated[
                bool,
                _Option("--reload", help="Watch and reload on file changes (dev only)"),
            ] = False,
        ) -> None:
            code = cmd_self.handle(Context())
            if code != 0:
                raise typer.Exit(code)
            cmd_self.serve(host=host, port=port, workers=workers, reload=reload)

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        if find_project_root() is None:
            ctx.error(
                "serve requires an Arvel project context (bootstrap/app.py not found "
                "in the current directory or its ancestors)."
            )
            return 2
        return 0

    def serve(
        self,
        *,
        host: str,
        port: int,
        reload: bool,
        workers: int | None = None,
    ) -> None:
        _make_app_importable()
        timeout = _graceful_shutdown_timeout()
        # uvicorn defaults timeout_graceful_shutdown to None, so passing None is a no-op.
        uvicorn.run(
            "public.asgi:asgi",
            host=host,
            port=port,
            reload=reload,
            workers=workers,
            timeout_graceful_shutdown=timeout,
        )


__all__ = ["ServeCommand"]
