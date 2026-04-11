"""Dev server — uvicorn with proxy-aware defaults."""

from __future__ import annotations

import os
import sys
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Annotated
from urllib.parse import urljoin

import typer

from arvel.cli.exceptions import ArvelCLIError
from arvel.cli.logging import get_uvicorn_log_config

serve_app = typer.Typer(
    name="serve", help="Start the development server.", invoke_without_command=True
)

_ENTRYPOINT = "bootstrap.app:create_app"


def _discover_app(base_path: Path | None = None) -> str:
    """Ensure bootstrap/app.py exists and return the ASGI import path.

    Args:
        base_path: Project root directory. Defaults to CWD.
    """
    root = base_path or Path.cwd()
    if not (root / "bootstrap" / "app.py").is_file():
        raise ArvelCLIError(
            "bootstrap/app.py not found. Every Arvel app must have this file "
            "with a create_app() factory. Use --app to override."
        )
    return _ENTRYPOINT


def _ensure_cwd_importable(app_dir: Path | None = None) -> None:
    """Put *app_dir* (or CWD) on sys.path so uvicorn workers can import the app."""
    target = str((app_dir or Path.cwd()).resolve())
    if target not in sys.path:
        sys.path.insert(0, target)
    existing = os.environ.get("PYTHONPATH", "")
    if target not in existing.split(os.pathsep):
        os.environ["PYTHONPATH"] = f"{target}{os.pathsep}{existing}" if existing else target


def _activate_project_venv(app_dir: Path) -> None:
    """Add the project's .venv site-packages to sys.path if present.

    When arvel is installed globally but the project has its own virtualenv,
    the project's dependencies won't be importable unless we inject them.
    """
    for venv_name in (".venv", "venv"):
        venv_dir = app_dir / venv_name
        if not venv_dir.is_dir():
            continue

        lib_dir = venv_dir / "lib"
        if not lib_dir.is_dir():
            continue

        for child in lib_dir.iterdir():
            sp = child / "site-packages"
            if sp.is_dir():
                sp_str = str(sp)
                if sp_str not in sys.path:
                    sys.path.insert(0, sp_str)
                os.environ["VIRTUAL_ENV"] = str(venv_dir)
                return


def _get_arvel_version() -> str:
    try:
        return pkg_version("arvel")
    except Exception:
        return "dev"


def _print_startup_banner(
    *,
    host: str,
    port: int,
    workers: int,
    use_reload: bool,
    root_path: str,
    base_path: Path | None = None,
) -> None:
    """Show the server banner with app name, env, and URLs."""
    from arvel.app.config import AppSettings
    from arvel.cli.app import BANNER
    from arvel.foundation.config import resolve_env_files, with_env_files

    base_path = (base_path or Path.cwd()).resolve()
    env_files = resolve_env_files(base_path)

    try:
        config = with_env_files(AppSettings, env_files, base_path=base_path)
    except Exception:
        config = AppSettings(base_path=base_path)

    app_name = config.app_name
    app_env = config.app_env
    app_debug = config.app_debug
    arvel_version = _get_arvel_version()

    green = typer.colors.GREEN
    cyan = typer.colors.CYAN
    yellow = typer.colors.YELLOW
    red = typer.colors.RED
    dim = typer.colors.BRIGHT_BLACK

    server_url = f"http://{host}:{port}"
    docs_path = config.app_docs_url
    redoc_path = config.app_redoc_url

    env_color = yellow if app_env == "development" else green
    debug_label = typer.style("ON", fg=red, bold=True) if app_debug else "OFF"

    typer.echo(typer.style(BANNER, fg=cyan, bold=True))
    typer.echo(f"  {typer.style(f'v{arvel_version}', fg=dim)}")
    typer.echo()
    typer.echo(f"  Server    {typer.style(server_url, fg=green, bold=True)}")
    typer.echo(f"  Docs      {typer.style(f'{urljoin(server_url, docs_path)}', fg=green)}")
    typer.echo(f"  ReDoc     {typer.style(f'{urljoin(server_url, redoc_path)}', fg=green)}")
    typer.echo()
    typer.echo(f"  App       {typer.style(app_name, fg=cyan, bold=True)}")
    typer.echo(f"  Env       {typer.style(app_env, fg=env_color)}")
    typer.echo(f"  Debug     {debug_label}")
    typer.echo(f"  Workers   {workers}")
    typer.echo(f"  Reload    {'ON' if use_reload else 'OFF'}")
    if root_path:
        typer.echo(f"  Root path {root_path}")
    typer.echo()
    typer.echo(typer.style("  Press Ctrl+C to stop", fg=dim))
    typer.echo()


@serve_app.callback(invoke_without_command=True)
def serve(
    host: Annotated[str, typer.Option("--host", "-h", help="Bind address.")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", "-p", help="Bind port.", envvar="PORT")] = 8000,
    reload: Annotated[
        bool, typer.Option("--reload/--no-reload", help="Auto-reload on file changes.")
    ] = True,
    workers: Annotated[
        int, typer.Option("--workers", "-w", help="Number of worker processes.")
    ] = 1,
    app_path: Annotated[
        str | None, typer.Option("--app", help="ASGI application import path (module:attr).")
    ] = None,
    app_dir: Annotated[
        Path,
        typer.Option(
            "--app-dir",
            help="Project root directory for import resolution.",
            exists=True,
            file_okay=False,
        ),
    ] = Path(),
    root_path: Annotated[
        str, typer.Option("--root-path", help="ASGI root_path for apps behind a reverse proxy.")
    ] = "",
    proxy_headers: Annotated[
        bool,
        typer.Option(
            "--proxy-headers/--no-proxy-headers",
            help="Trust X-Forwarded-Proto/For/Host headers from a reverse proxy.",
        ),
    ] = True,
    forwarded_allow_ips: Annotated[
        str | None,
        typer.Option(
            "--forwarded-allow-ips",
            help="Comma-separated IPs trusted to set proxy headers (default: 127.0.0.1).",
        ),
    ] = None,
    reload_dir: Annotated[
        list[Path] | None,
        typer.Option(
            "--reload-dir",
            help="Directory to watch for changes (repeatable). Implies --reload.",
            exists=True,
            file_okay=False,
        ),
    ] = None,
) -> None:
    """Start the dev server via uvicorn."""
    try:
        import uvicorn
    except ImportError:
        typer.echo(
            "Error: uvicorn is not installed. Install it with: pip install uvicorn[standard]"
        )
        raise typer.Exit(code=1) from None

    root_path = root_path or ""
    resolved_dir = app_dir.resolve()

    use_factory = False
    try:
        if app_path:
            import_string = app_path
        else:
            import_string = _discover_app(base_path=resolved_dir)
            use_factory = True
    except ArvelCLIError as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(code=1) from None

    use_reload = reload or bool(reload_dir)
    reload_dirs_str: list[str] | None = None
    if reload_dir:
        reload_dirs_str = [str(d.resolve()) for d in reload_dir]

    _activate_project_venv(resolved_dir)
    _ensure_cwd_importable(resolved_dir)

    _print_startup_banner(
        host=host,
        port=port,
        workers=workers,
        use_reload=use_reload,
        root_path=root_path,
        base_path=resolved_dir,
    )

    uvicorn.run(
        import_string,
        host=host,
        port=port,
        reload=use_reload,
        reload_dirs=reload_dirs_str,
        workers=workers,
        root_path=root_path,
        proxy_headers=proxy_headers,
        forwarded_allow_ips=forwarded_allow_ips,
        factory=use_factory,
        log_config=get_uvicorn_log_config(),
    )
