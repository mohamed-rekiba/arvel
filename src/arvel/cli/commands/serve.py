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

serve_app = typer.Typer(
    name="serve", help="Start the development server.", invoke_without_command=True
)

_ENTRYPOINT = "bootstrap.app:create_app"


def _discover_app() -> str:
    """Ensure bootstrap/app.py exists and return the ASGI import path."""
    if not Path("bootstrap/app.py").is_file():
        raise ArvelCLIError(
            "bootstrap/app.py not found. Every Arvel app must have this file "
            "with a create_app() factory. Use --app to override."
        )
    return _ENTRYPOINT


def _ensure_cwd_importable() -> None:
    """Put CWD on sys.path so uvicorn workers can import the app."""
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    existing = os.environ.get("PYTHONPATH", "")
    if cwd not in existing.split(os.pathsep):
        os.environ["PYTHONPATH"] = f"{cwd}{os.pathsep}{existing}" if existing else cwd


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
) -> None:
    """Show the server banner with app name, env, and URLs."""
    from arvel.app.config import AppSettings
    from arvel.cli.app import BANNER
    from arvel.foundation.config import resolve_env_files, with_env_files

    base_path = Path.cwd()
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
    port: Annotated[int, typer.Option("--port", "-p", help="Bind port.")] = 8000,
    reload: Annotated[
        bool, typer.Option("--reload/--no-reload", help="Auto-reload on file changes.")
    ] = True,
    workers: Annotated[
        int, typer.Option("--workers", "-w", help="Number of worker processes.")
    ] = 1,
    app_path: Annotated[
        str | None, typer.Option("--app", help="ASGI application import path (module:attr).")
    ] = "bootstrap.app:create_app",
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

    try:
        import_string = app_path if app_path else _discover_app()
    except ArvelCLIError as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(code=1) from None

    use_reload = reload or bool(reload_dir)
    reload_dirs_str: list[str] | None = None
    if reload_dir:
        reload_dirs_str = [str(d.resolve()) for d in reload_dir]

    _ensure_cwd_importable()

    _print_startup_banner(
        host=host,
        port=port,
        workers=workers,
        use_reload=use_reload,
        root_path=root_path,
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
        factory=True,
        log_config=None,
    )
