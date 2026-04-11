"""Scaffold a new Arvel project from a GitHub template."""

from __future__ import annotations

import re
from pathlib import Path

import typer

from arvel.cli.plugins._base import CliPlugin  # noqa: TC001

_new_app = typer.Typer(name="new", help="Create a new Arvel project.")


def validate_project_name(name: str) -> bool:
    """True if name works as a directory and Python package name."""
    if not name:
        return False
    normalized = name.replace("-", "_")
    return bool(re.match(r"^[a-z_][a-z0-9_]*$", normalized))


def _validate_choice(option: str, value: str, configs: dict[str, dict[str, str]]) -> None:
    """Raise CliValidationError if value isn't in configs."""
    from arvel.cli.exceptions import CliValidationError

    if value not in configs:
        choices = ", ".join(configs)
        msg = f"Unknown {option} '{value}'. Choose: {choices}."
        raise CliValidationError(msg)


def _validate_inputs(
    *,
    name: str,
    force: bool,
    preset: str | None,
    database: str,
    cache: str,
    queue: str,
    mail: str,
    storage: str,
    search: str,
    broadcast: str,
) -> Path:
    """Validate all CLI arguments and return the target directory."""
    from arvel.cli.exceptions import CliValidationError

    from .config import (
        BROADCAST_CONFIGS,
        CACHE_CONFIGS,
        DATABASE_CONFIGS,
        MAIL_CONFIGS,
        PRESETS,
        QUEUE_CONFIGS,
        SEARCH_CONFIGS,
        STORAGE_CONFIGS,
    )

    if not validate_project_name(name):
        msg = "Invalid project name. Use lowercase letters, digits, hyphens, and underscores."
        raise CliValidationError(msg)

    target = Path.cwd() / name
    if target.exists() and not force:
        msg = f"Directory '{name}' already exists. Use --force to overwrite."
        raise CliValidationError(msg)

    if preset and preset not in PRESETS:
        valid = ", ".join(PRESETS)
        msg = f"Unknown preset '{preset}'. Choose: {valid}."
        raise CliValidationError(msg)

    _validate_choice("database", database, DATABASE_CONFIGS)
    _validate_choice("cache", cache, CACHE_CONFIGS)
    _validate_choice("queue", queue, QUEUE_CONFIGS)
    _validate_choice("mail", mail, MAIL_CONFIGS)
    _validate_choice("storage", storage, STORAGE_CONFIGS)
    _validate_choice("search", search, SEARCH_CONFIGS)
    _validate_choice("broadcast", broadcast, BROADCAST_CONFIGS)
    return target


def new_project(
    name: str = typer.Argument(help="Project name (directory name)."),
    database: str = typer.Option(
        "sqlite",
        "--database",
        "-d",
        help="Database driver: sqlite, postgres, mysql.",
    ),
    cache: str = typer.Option(
        "memory",
        "--cache",
        help="Cache driver: memory, redis.",
    ),
    queue: str = typer.Option(
        "sync",
        "--queue",
        help="Queue driver: sync, redis, taskiq.",
    ),
    mail: str = typer.Option(
        "log",
        "--mail",
        help="Mail driver: log, smtp.",
    ),
    storage: str = typer.Option(
        "local",
        "--storage",
        help="Storage driver: local, s3.",
    ),
    search: str = typer.Option(
        "collection",
        "--search",
        help="Search driver: collection, meilisearch, elasticsearch.",
    ),
    broadcast: str = typer.Option(
        "memory",
        "--broadcast",
        help="Broadcast driver: memory, redis, log, null.",
    ),
    preset: str | None = typer.Option(
        None,
        "--preset",
        "-p",
        help="Stack preset: minimal, standard, full.",
    ),
    no_git: bool = typer.Option(False, "--no-git", help="Skip git initialization."),
    branch: str | None = typer.Option(None, "--branch", "-b", help="Template repo branch or tag."),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing directory."),
    no_install: bool = typer.Option(False, "--no-install", help="Skip uv sync."),
    template: str | None = typer.Option(
        None, "--template", "-t", help="Template name from the registry (default: 'default')."
    ),
    using: str | None = typer.Option(
        None, "--using", help="Custom template repo URL (bypasses registry)."
    ),
    no_input: bool = typer.Option(False, "--no-input", help="Skip interactive prompts."),
) -> None:
    """Create a new Arvel project."""
    from arvel.cli.exceptions import CliValidationError
    from arvel.cli.ui import BANNER, InquirerPreloader

    preloader = InquirerPreloader() if not no_input else None

    try:
        target = _validate_inputs(
            name=name,
            force=force,
            preset=preset,
            database=database,
            cache=cache,
            queue=queue,
            mail=mail,
            storage=storage,
            search=search,
            broadcast=broadcast,
        )
    except CliValidationError as exc:
        if preloader is not None:
            preloader.stop()
        typer.echo(exc.message)
        raise typer.Exit(code=1) from None

    from . import templates as _tpl
    from .config import PRESETS
    from .prompts import _run_interactive_prompts
    from .scaffold import (
        _build_context,
        _git_init,
        _run_uv_sync,
        _setup_env,
        render_skeleton,
        to_package_name,
    )
    from .templates import _await_download, _start_background_download

    if using:
        repo_url = using
    else:
        templates = _tpl._fetch_templates_registry()
        repo_url = _tpl._resolve_template_repo(templates, template)

    download_future = _start_background_download(repo_url, branch)

    from rich.console import Console

    console = Console()

    if no_input or preloader is None:
        base = PRESETS[preset] if preset else PRESETS["minimal"]
        driver_choices = {
            "database": database if database != "sqlite" or not preset else base["database"],
            "cache": cache if cache != "memory" or not preset else base["cache"],
            "queue": queue if queue != "sync" or not preset else base["queue"],
            "mail": mail if mail != "log" or not preset else base["mail"],
            "storage": storage if storage != "local" or not preset else base["storage"],
            "search": search if search != "collection" or not preset else base["search"],
            "broadcast": broadcast if broadcast != "memory" or not preset else base["broadcast"],
        }
    else:
        driver_choices = _run_interactive_prompts(
            cli_database=database,
            cli_cache=cache,
            cli_queue=queue,
            cli_mail=mail,
            cli_storage=storage,
            cli_search=search,
            cli_broadcast=broadcast,
            cli_preset=preset,
            preloader=preloader,
            console=console,
        )

    console.print(f"[bold cyan]{BANNER}[/bold cyan]")
    console.print(f"  Creating [bold]{name}[/bold]\n")

    skeleton_dir = _await_download(download_future, console)
    console.print("  [green]✓[/green] Template downloaded")

    package_name = to_package_name(name)
    context = _build_context(driver_choices, package_name)

    with console.status(
        "[bold cyan]  Scaffolding project...[/bold cyan]",
        spinner="dots",
    ):
        render_skeleton(
            skeleton_dir=skeleton_dir,
            target_dir=target,
            context=context,
        )
        _setup_env(target, context)

        if driver_choices["database"] == "sqlite":
            db_dir = target / "database"
            db_dir.mkdir(exist_ok=True)
            (db_dir / "database.sqlite").touch()

    console.print("  [green]✓[/green] Project scaffolded")

    if not no_install:
        with console.status(
            "[bold cyan]  Installing dependencies...[/bold cyan]",
            spinner="dots",
        ):
            _run_uv_sync(target)
        console.print("  [green]✓[/green] Dependencies installed")

    if not no_git:
        with console.status(
            "[bold cyan]  Initializing git...[/bold cyan]",
            spinner="dots",
        ):
            _git_init(target)
        console.print("  [green]✓[/green] Git initialized")

    console.print()
    console.print("  [bold green]✓ Application ready![/bold green] Build something amazing.")
    console.print()
    console.print(f"  [dim]$[/dim] cd {name}")
    console.print("  [dim]$[/dim] uv run arvel serve")
    console.print("  [dim]$[/dim] uv run arvel make module <your-first-module>")
    console.print()


class _Plugin:
    name = "new"
    help = "Create a new Arvel project."

    def register(self, app: typer.Typer) -> None:
        app.add_typer(_new_app, name=self.name)


plugin: CliPlugin = _Plugin()  # type: ignore[assignment]
