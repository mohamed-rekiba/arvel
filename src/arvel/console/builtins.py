"""Built-in T0 commands (no app boot): about / extras / new / down / up.

Each is a single-command ``typer.Typer`` app; ``LazyGroup`` converts it to a
mountable command via ``typer.main.get_command`` only when invoked. (typer 0.26
vendors click as ``typer._click``, so commands must be Typer-built to mount.)
``new`` scaffolds a real app/package tree (stdlib only — no boot, stays T0-fast).
"""

from __future__ import annotations

from typing import Any

import typer

about_app = typer.Typer()


@about_app.command()
def about() -> None:
    """Show framework info + banner."""
    from arvel import __version__
    from arvel.console.banner import print_banner
    from arvel.console.context import console_mode

    print_banner(__version__)
    typer.echo("arvel — a batteries-included async web framework for Python")
    typer.echo(f"version: {__version__} · async-first · type-safe · modular")
    typer.echo(f"mode: {console_mode()}  ({_discovered_summary()})")


def _discovered_summary() -> str:
    """A short, no-boot summary of discovered ecosystem packages (cached manifest vs live scan)."""
    from arvel.kernel.discovery import manifest_path

    if manifest_path().is_file():
        return "packages: cached manifest"
    import importlib.metadata as md

    count = sum(1 for _ in md.entry_points(group="arvel.providers"))
    return f"packages: {count} discovered (run `package:discover` to cache)"


extras_app = typer.Typer()


@extras_app.command()
def extras() -> None:
    """List the optional dependency extras."""
    names = [
        "http",
        "server",
        "postgres",
        "mysql",
        "sqlite",
        "redis",
        "queue",
        "view",
        "auth",
        "jwt",
        "oauth",
        "2fa",
        "rbac",
        "s3",
        "gcs",
        "azure",
        "image",
        "video",
        "media",
        "mail",
        "notifications",
        "i18n",
    ]
    typer.echo("arvel extras (uv add 'arvel[<extra>]'):")
    typer.echo("  " + ", ".join(names))


new_app = typer.Typer()


def _pkg_provider(name: str) -> str:
    cls = "".join(p.capitalize() for p in name.replace("-", "_").split("_")) + "ServiceProvider"
    return (
        '"""Service provider — auto-registered via the arvel.providers entry point."""\n\n'
        "from arvel.kernel import ServiceProvider\n\n\n"
        f"class {cls}(ServiceProvider):\n"
        "    def register(self) -> None:\n"
        f'        self.app.singleton("{name}", lambda c: object())\n\n'
        "    def boot(self) -> None:\n"
        "        ...\n"
    )


def _pkg_pyproject(name: str) -> str:
    mod = "arvel_" + name.replace("-", "_")
    cls = "".join(p.capitalize() for p in name.replace("-", "_").split("_")) + "ServiceProvider"
    return (
        "[project]\n"
        f'name = "arvel-{name}"\n'
        'version = "0.1.0"\n'
        'requires-python = ">=3.14"\n'
        'dependencies = ["arvel"]\n\n'
        '[project.entry-points."arvel.providers"]\n'
        f'{name} = "{mod}.provider:{cls}"\n'
    )


def _write_tree(root: Any, files: dict[str, str]) -> int:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return len(files)


def _copy_skeleton(kind: str, target: Any, subs: dict[str, str]) -> int:
    """Copy the packaged skeleton tree ``_skeleton/<kind>`` into ``target``.

    Skeleton files are stored as ``.tmpl`` data (so the Python tooling — ruff/mypy/pyright/
    import-linter/pytest — ignores them); on copy the ``.tmpl`` suffix is stripped, a ``dot.`` prefix
    becomes ``.`` (for dotfiles), and ``{{key}}`` tokens are substituted.
    """
    from pathlib import Path

    root = Path(__file__).parent / "_skeleton" / kind
    count = 0
    for src in sorted(root.rglob("*.tmpl")):
        if "__pycache__" in src.parts:
            continue
        parts = list(src.relative_to(root).parts)
        leaf = parts[-1].removesuffix(".tmpl")
        if leaf.startswith("dot."):
            leaf = "." + leaf[len("dot.") :]
        parts[-1] = leaf
        text = src.read_text()
        for key, value in subs.items():
            text = text.replace("{{" + key + "}}", value)
        dest = target / Path(*parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
        count += 1
    return count


@new_app.command()
def new(
    name: str,
    package: bool = typer.Option(False, "--package", help="Scaffold an ecosystem package."),
    profile: str = typer.Option("api", "--profile", help="App shape: api|web|inertia-vue|minimal."),
    auth: bool = typer.Option(
        False, "--auth", help="Scaffold a bearer-token auth flow (login + protected route)."
    ),
) -> None:
    """Scaffold a new arvel app or ecosystem package."""
    from pathlib import Path

    target = Path(name)
    if target.exists():
        typer.echo(f"{name!r} already exists")
        raise typer.Exit(1)

    if package:
        files = {
            "pyproject.toml": _pkg_pyproject(name),
            f"src/arvel_{name.replace('-', '_')}/__init__.py": "",
            f"src/arvel_{name.replace('-', '_')}/provider.py": _pkg_provider(name),
            "README.md": f"# arvel-{name}\n\nAn arvel ecosystem package.\n",
        }
        count = _write_tree(target, files)
        typer.echo(f"[arvel new] created package arvel-{name} ({count} files)")
        return

    count = _copy_skeleton("app", target, {"name": name})
    if profile in ("web", "inertia-vue"):
        views = target / "resources" / "views"
        views.mkdir(parents=True, exist_ok=True)
        (views / "welcome.html").write_text(f"<h1>Welcome to {name}</h1>\n")
        count += 1
    if auth:
        # overlay the bearer-token auth flow (overwrites routes/api.py, adds the auth test)
        count += _copy_skeleton("auth", target, {"name": name})
    label = f"{profile}+auth" if auth else profile
    typer.echo(f"[arvel new] created app {name!r} (profile: {label}, {count} files)")
    typer.echo(f"  cd {name} && uv sync")
    typer.echo("  source .venv/bin/activate")
    typer.echo("  arvel serve --reload")


down_app = typer.Typer()


@down_app.command()
def down() -> None:
    """Put the application into maintenance mode (flag stored in the APP's default cache —
    booted through the project app so a redis/valkey store reaches every server process; an
    app-less write would land in a CLI-process-local array cache and die with the process)."""
    from arvel.console.kernel import run_app_command

    async def _handler(app: object) -> None:
        from arvel.http.maintenance import down as enter_maintenance

        await enter_maintenance()
        typer.echo("application is now in maintenance mode (503)")

    run_app_command(_handler)


up_app = typer.Typer()


@up_app.command()
def up() -> None:
    """Bring the application out of maintenance mode (clears the flag in the APP's cache)."""
    from arvel.console.kernel import run_app_command

    async def _handler(app: object) -> None:
        from arvel.http.maintenance import up as leave_maintenance

        await leave_maintenance()
        typer.echo("application is live")

    run_app_command(_handler)


serve_app = typer.Typer()


def _serve_command(host: str, port: int, *, reload: bool, app: str) -> list[str]:
    """Build the ``python -m granian`` argv serving the app's ASGI entrypoint (pure → unit-testable).
    Run via ``sys.executable -m granian`` (not a bare ``granian``) so it works without the venv's
    bin on PATH."""
    import sys

    cmd = [
        sys.executable,
        "-m",
        "granian",
        "--interface",
        "asgi",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if reload:
        cmd.append("--reload")
    cmd.append(app)
    return cmd


@serve_app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host to bind."),
    port: int = typer.Option(8000, help="Port to bind."),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes (dev)."),
    app: str = typer.Option("asgi:asgi_app", help="ASGI app target (module:attr)."),
) -> None:
    """Run the development server (granian) serving the app's ASGI entrypoint."""
    # launch granian as a subprocess — a fixed argv list, no shell, no untrusted input
    import subprocess  # nosec B404

    cmd = _serve_command(host, port, reload=reload, app=app)
    typer.echo(f"[arvel serve] http://{host}:{port}  ({app}, granian)")
    try:
        # cmd is a fixed argv list (granian + the developer's own CLI flags); shell=False
        code = subprocess.call(cmd)  # nosec B603
        raise typer.Exit(code)
    except FileNotFoundError:
        typer.echo("granian not found — install the server extra: uv add 'arvel[server]'")
        raise typer.Exit(1) from None
