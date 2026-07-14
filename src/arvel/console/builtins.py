"""Built-in T0 commands (no app boot): about / extras / new / down / up.

Each is a single-command ``typer.Typer`` app; ``LazyGroup`` converts it to a
mountable command via ``typer.main.get_command`` only when invoked. (typer 0.26
vendors click as ``typer._click``, so commands must be Typer-built to mount.)
``new`` scaffolds a real app/package tree (stdlib only — no boot, stays T0-fast).
"""

from __future__ import annotations

import re
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


def _derive_package_name(raw: str) -> str:
    """The package/app name for a scaffold target (A8) — the **basename** of ``raw`` (so an
    absolute or relative path both work: ``arvel new /abs/path/my-app`` names the package
    ``my-app``, not the whole path), sanitized to a valid PEP 503 name. Empty/invalid input (e.g.
    a bare ``/`` or a name that's only punctuation) sanitizes to ``""`` — the caller must guard it."""
    from pathlib import Path

    basename = Path(raw).name
    return re.sub(r"[^a-z0-9]+", "-", basename.lower()).strip("-")


def _copy_skeleton(kind: str, target: Any, subs: dict[str, str]) -> int:
    """Copy the packaged skeleton tree ``_skeleton/<kind>`` into ``target``.

    Skeleton files are stored as ``.tmpl`` data (so the Python tooling — ruff/mypy/pyright/
    import-linter/pytest — ignores them); on copy the ``.tmpl`` suffix is stripped, a ``dot.`` prefix
    becomes ``.`` (for dotfiles), and ``{{key}}`` tokens are substituted — in file contents AND in
    path segments (so a template dir like ``src/{{mod}}/`` lands as ``src/arvel_stripe/``).
    """
    from pathlib import Path

    root = Path(__file__).parent / "_skeleton" / kind
    count = 0
    for src in sorted(root.rglob("*.tmpl")):
        if "__pycache__" in src.parts:
            continue
        parts = list(src.relative_to(root).parts)
        parts[-1] = parts[-1].removesuffix(".tmpl")
        # dot. -> . on every segment, so dotted DIRS (dot.github/) work too
        parts = ["." + p[len("dot.") :] if p.startswith("dot.") else p for p in parts]
        text = src.read_text()
        for key, value in subs.items():
            token = "{{" + key + "}}"
            text = text.replace(token, value)
            parts = [p.replace(token, value) for p in parts]
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
    pkg_name = _derive_package_name(name)
    if not pkg_name:
        typer.echo(f"{name!r} has no valid package name (its basename sanitizes to empty)")
        raise typer.Exit(1)
    if target.exists():
        typer.echo(f"{name!r} already exists")
        raise typer.Exit(1)

    if package:
        mod = "arvel_" + pkg_name.replace("-", "_")
        cls = "".join(p.capitalize() for p in pkg_name.replace("-", "_").split("_"))
        count = _copy_skeleton(
            "package", target, {"name": pkg_name, "mod": mod, "cls": cls}
        )
        typer.echo(f"[arvel new] created package arvel-{pkg_name} ({count} files)")
        typer.echo(f"  cd {name} && uv sync")
        typer.echo("  uv run pytest    # the un-pruned skeleton is green out of the box")
        typer.echo("  # then delete what you don't need — see README.md")
        return

    count = _copy_skeleton("app", target, {"name": pkg_name})
    if profile in ("web", "inertia-vue"):
        views = target / "resources" / "views"
        views.mkdir(parents=True, exist_ok=True)
        (views / "welcome.html").write_text(f"<h1>Welcome to {pkg_name}</h1>\n")
        count += 1
    if auth:
        # overlay the bearer-token auth flow (overwrites routes/api.py, adds the auth test)
        count += _copy_skeleton("auth", target, {"name": pkg_name})
    # a fresh app is born with working crypto: mirror .env.example into a live .env and
    # generate APP_KEY now — otherwise the encrypter (cookie encryption, encrypted casts)
    # is silently inert until someone remembers key:generate
    from arvel.console.ops import set_env_var
    from arvel.security import Encrypter

    env_file = target / ".env"
    example = target / ".env.example"
    if example.exists() and not env_file.exists():
        env_file.write_text(example.read_text())
        count += 1
    set_env_var(env_file, "APP_KEY", Encrypter.generate_key())
    label = f"{profile}+auth" if auth else profile
    typer.echo(f"[arvel new] created app {pkg_name!r} (profile: {label}, {count} files)")
    typer.echo(f"  cd {name} && uv sync")
    typer.echo("  source .venv/bin/activate")
    typer.echo("  arvel serve --reload")


down_app = typer.Typer()


@down_app.command()
def down(
    message: str = typer.Option(
        "Down for maintenance.", "--message", help="The message shown to visitors."
    ),
    retry: int = typer.Option(60, "--retry", help="Retry-After seconds hint."),
    secret: str | None = typer.Option(
        None,
        "--secret",
        help="A bypass token: a request with ?secret=<token> (and its follow-up cookie) gets through.",
    ),
    allow: list[str] = typer.Option(
        [], "--allow", help="An IP allowed through unrestricted (repeatable)."
    ),
    render: str | None = typer.Option(
        None,
        "--render",
        help="Pre-render resources/views/<name>.html into the maintenance payload.",
    ),
) -> None:
    """Put the application into maintenance mode (flag stored in the APP's default cache —
    booted through the project app so a redis/valkey store reaches every server process; an
    app-less write would land in a CLI-process-local array cache and die with the process)."""
    from arvel.console.kernel import run_app_command

    async def _handler(app: object) -> None:
        from arvel.http.maintenance import down as enter_maintenance

        await enter_maintenance(message, retry, secret, allow, render)
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
    import subprocess  # nosec B404

    cmd = _serve_command(host, port, reload=reload, app=app)
    typer.echo(f"[arvel serve] http://{host}:{port}  ({app}, granian)")
    try:
        # fixed argv list, no shell=True — nothing here is untrusted input
        code = subprocess.call(cmd)  # nosec B603
        raise typer.Exit(code)
    except FileNotFoundError:
        typer.echo("granian not found — install the server extra: uv add 'arvel[server]'")
        raise typer.Exit(1) from None
