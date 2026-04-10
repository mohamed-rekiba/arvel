"""arvel new — scaffold a new Arvel project from a GitHub template.

Fetches the starters registry from the latest framework release to resolve
the template repo URL, downloads the skeleton tarball, renders Jinja2
templates, and optionally runs uv sync + git init.
"""

from __future__ import annotations

import io
import json
import re
import secrets
import shutil
import subprocess
import tarfile
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import typer
from jinja2 import Environment, FileSystemLoader

new_app = typer.Typer(name="new", help="Create a new Arvel project.")

FRAMEWORK_REPO = "mohamed-rekiba/arvel"
TEMPLATES_ASSET = "templates.json"

DATABASE_CONFIGS: dict[str, dict[str, str]] = {
    "sqlite": {
        "driver": "sqlite",
        "sa_driver": "sqlite+aiosqlite",
        "url_template": "sqlite+aiosqlite:///database/database.sqlite",
        "extra": "sqlite",
        "db_host": "127.0.0.1",
        "db_port": "",
        "db_username": "",
        "db_database": "database/database.sqlite",
    },
    "postgres": {
        "driver": "pgsql",
        "sa_driver": "postgresql+asyncpg",
        "url_template": "postgresql+asyncpg://localhost:5432/{app_name}",
        "extra": "pg",
        "db_host": "127.0.0.1",
        "db_port": "5432",
        "db_username": "arvel",
        "db_database": "{app_name}",
    },
    "mysql": {
        "driver": "mysql",
        "sa_driver": "mysql+aiomysql",
        "url_template": "mysql+aiomysql://localhost:3306/{app_name}",
        "extra": "mysql",
        "db_host": "127.0.0.1",
        "db_port": "3306",
        "db_username": "arvel",
        "db_database": "{app_name}",
    },
}

CACHE_CONFIGS: dict[str, dict[str, str]] = {
    "memory": {"driver": "memory", "extra": ""},
    "redis": {"driver": "redis", "extra": "redis"},
}

QUEUE_CONFIGS: dict[str, dict[str, str]] = {
    "sync": {"driver": "sync", "extra": ""},
    "redis": {"driver": "redis", "extra": "redis"},
    "taskiq": {"driver": "taskiq", "extra": "taskiq"},
}

MAIL_CONFIGS: dict[str, dict[str, str]] = {
    "log": {"driver": "log", "extra": ""},
    "smtp": {"driver": "smtp", "extra": "smtp"},
}

STORAGE_CONFIGS: dict[str, dict[str, str]] = {
    "local": {"driver": "local", "extra": ""},
    "s3": {"driver": "s3", "extra": "s3"},
}

SEARCH_CONFIGS: dict[str, dict[str, str]] = {
    "collection": {"driver": "collection", "extra": ""},
    "meilisearch": {"driver": "meilisearch", "extra": "meilisearch"},
    "elasticsearch": {"driver": "elasticsearch", "extra": "elasticsearch"},
}

BROADCAST_CONFIGS: dict[str, dict[str, str]] = {
    "memory": {"driver": "memory", "extra": ""},
    "redis": {"driver": "redis", "extra": "redis"},
    "log": {"driver": "log", "extra": ""},
    "null": {"driver": "null", "extra": ""},
}

_VALID_CHOICES: dict[str, dict[str, dict[str, str]]] = {
    "database": DATABASE_CONFIGS,
    "cache": CACHE_CONFIGS,
    "queue": QUEUE_CONFIGS,
    "mail": MAIL_CONFIGS,
    "storage": STORAGE_CONFIGS,
    "search": SEARCH_CONFIGS,
    "broadcast": BROADCAST_CONFIGS,
}


PRESETS: dict[str, dict[str, str]] = {
    "minimal": {
        "database": "sqlite",
        "cache": "memory",
        "queue": "sync",
        "mail": "log",
        "storage": "local",
        "search": "collection",
        "broadcast": "memory",
    },
    "standard": {
        "database": "postgres",
        "cache": "redis",
        "queue": "redis",
        "mail": "smtp",
        "storage": "local",
        "search": "collection",
        "broadcast": "memory",
    },
    "full": {
        "database": "postgres",
        "cache": "redis",
        "queue": "taskiq",
        "mail": "smtp",
        "storage": "s3",
        "search": "meilisearch",
        "broadcast": "redis",
    },
}

_SERVICE_LABELS: dict[str, str] = {
    "database": "Database",
    "cache": "Cache",
    "queue": "Queue",
    "mail": "Mail",
    "storage": "Storage",
    "search": "Search",
    "broadcast": "Broadcast",
}


def _collect_extras(choices: dict[str, str]) -> list[str]:
    """Collect unique arvel extras from all driver choices."""
    extras: set[str] = set()
    for option_name, chosen_value in choices.items():
        configs = _VALID_CHOICES[option_name]
        cfg = configs[chosen_value]
        extra = cfg.get("extra", "")
        if extra:
            extras.add(extra)
    return sorted(extras)


def _prompt_select(message: str, choices: list[dict[str, str]], default: str | None = None) -> str:
    """Arrow-key select prompt powered by InquirerPy."""
    from InquirerPy import inquirer

    return inquirer.select(  # type: ignore[no-any-return]
        message=message,
        choices=choices,
        default=default,
        pointer="❯",  # noqa: RUF001
        show_cursor=False,
    ).execute()


def _preset_summary(preset_name: str) -> str:
    """Build a short summary string for a preset."""
    p = PRESETS[preset_name]
    return ", ".join(f"{p[k]}" for k in _SERVICE_LABELS)


def _run_interactive_prompts(
    *,
    cli_database: str,
    cli_cache: str,
    cli_queue: str,
    cli_mail: str,
    cli_storage: str,
    cli_search: str,
    cli_broadcast: str,
    cli_preset: str | None,
) -> dict[str, str]:
    """Run the interactive stack selection flow.

    Any value explicitly passed on the CLI is locked and not prompted.
    Returns a dict with keys matching ``_SERVICE_LABELS``.
    """
    cli_overrides: dict[str, str] = {}
    defaults = PRESETS["minimal"]
    service_to_cli = {
        "database": cli_database,
        "cache": cli_cache,
        "queue": cli_queue,
        "mail": cli_mail,
        "storage": cli_storage,
        "search": cli_search,
        "broadcast": cli_broadcast,
    }

    for svc, cli_val in service_to_cli.items():
        if cli_val != defaults[svc]:
            cli_overrides[svc] = cli_val

    if cli_preset and cli_preset in PRESETS:
        choices = {**PRESETS[cli_preset], **cli_overrides}
    elif cli_overrides:
        choices = {**defaults, **cli_overrides}
        return choices
    else:
        preset_choices = [
            {"name": f"Minimal    — {_preset_summary('minimal')}", "value": "minimal"},
            {"name": f"Standard   — {_preset_summary('standard')}", "value": "standard"},
            {"name": f"Full       — {_preset_summary('full')}", "value": "full"},
            {"name": "Custom     — choose each service individually", "value": "custom"},
        ]

        selected = _prompt_select(
            "Choose your stack:",
            preset_choices,
            default="minimal",
        )

        if selected == "custom":
            choices = _run_custom_prompts(cli_overrides)
        else:
            choices = {**PRESETS[selected], **cli_overrides}

    _print_summary(choices)
    return choices


def _run_custom_prompts(cli_overrides: dict[str, str]) -> dict[str, str]:
    """Prompt for each service individually, skipping those already set via CLI."""
    choices: dict[str, str] = {}
    defaults = PRESETS["minimal"]

    for svc, label in _SERVICE_LABELS.items():
        if svc in cli_overrides:
            choices[svc] = cli_overrides[svc]
            continue
        configs = _VALID_CHOICES[svc]
        option_list = [{"name": k, "value": k} for k in configs]
        choices[svc] = _prompt_select(f"{label}:", option_list, default=defaults[svc])

    return choices


def _print_summary(choices: dict[str, str]) -> None:
    """Print a compact summary of the selected stack."""
    parts = [f"[green]{choices[svc]}[/green]" for svc in _SERVICE_LABELS]
    summary = " · ".join(parts)
    typer.echo()
    from rich.console import Console

    Console().print(f"  [bold]Stack:[/bold] {summary}")
    typer.echo()


def validate_project_name(name: str) -> bool:
    """Check that name is a valid directory/package name."""
    if not name:
        return False
    normalized = name.replace("-", "_")
    return bool(re.match(r"^[a-z_][a-z0-9_]*$", normalized))


def to_package_name(name: str) -> str:
    """Convert kebab-case or raw name to a valid Python package name."""
    return name.replace("-", "_").lower()


def to_pascal_case(name: str) -> str:
    """Convert snake_case or kebab-case to PascalCase."""
    parts = name.replace("-", "_").split("_")
    return "".join(p.capitalize() for p in parts)


def _generate_secret_key() -> str:
    """Generate a 64-character hex secret key."""
    return secrets.token_hex(32)


def _get_arvel_version() -> str:
    """Get the current arvel framework version."""
    try:
        from importlib.metadata import version

        return version("arvel")
    except Exception:
        return "0.1.0"


def _fetch_templates_registry() -> list[dict[str, Any]]:
    """Fetch templates.json from the latest framework release on GitHub.

    The newest release is always marked as ``latest`` so this URL is stable.
    Falls back to the bundled templates.json shipped with the framework.
    """
    url = f"https://github.com/{FRAMEWORK_REPO}/releases/latest/download/{TEMPLATES_ASSET}"
    req = Request(url, headers={"User-Agent": "arvel-cli"})  # noqa: S310

    try:
        with urlopen(req, timeout=15) as response:  # noqa: S310
            data = json.loads(response.read())
            return data.get("templates", [])
    except Exception:
        return _load_bundled_registry()


def _load_bundled_registry() -> list[dict[str, Any]]:
    """Load templates.json bundled inside the arvel package (offline fallback)."""
    import importlib.resources

    try:
        ref = importlib.resources.files("arvel").joinpath("templates.json")
        data = json.loads(ref.read_text(encoding="utf-8"))
        return data.get("templates", [])
    except Exception:
        return []


def _resolve_template_repo(templates: list[dict[str, Any]], name: str | None = None) -> str:
    """Find the repo URL for a template by name, or the default template."""
    if name:
        for t in templates:
            if t.get("name") == name:
                return t["repo"]
        available = ", ".join(t.get("name", "?") for t in templates)
        raise SystemExit(f"Unknown template '{name}'. Available: {available}")

    for t in templates:
        if t.get("default"):
            return t["repo"]

    if templates:
        return templates[0]["repo"]
    raise SystemExit("No templates found in registry.")


def _repo_to_owner_name(repo_url: str) -> str:
    """Extract 'owner/repo' from a GitHub URL."""
    repo_url = repo_url.rstrip("/")
    if repo_url.startswith("https://github.com/"):
        return repo_url.removeprefix("https://github.com/")
    return repo_url


def _download_skeleton(
    repo_url: str,
    branch: str | None = None,
) -> Path:
    """Download and extract the template repo tarball. Returns path to extracted dir.

    Tries the GitHub tarball API first. If that fails (private repo, no network,
    etc.), falls back to ``git clone``. Raises ``SystemExit`` only when both
    strategies fail.
    """
    owner_repo = _repo_to_owner_name(repo_url)

    if branch is None:
        branch = _resolve_latest_tag(owner_repo)

    path = _download_skeleton_tarball(owner_repo, branch)
    if path is not None:
        return path

    path = _download_skeleton_git_clone(repo_url, branch)
    if path is not None:
        return path

    raise SystemExit(
        f"Could not download template from '{repo_url}'.\n"
        "  • Check your internet connection\n"
        "  • Verify the template repo exists and is accessible\n"
        "  • Use --using <url> to specify a custom template repo"
    )


def _download_skeleton_tarball(owner_repo: str, branch: str) -> Path | None:
    """Try downloading via the GitHub tarball API. Returns None on failure."""
    url = f"https://github.com/{owner_repo}/tarball/{branch}"
    req = Request(url, headers={"User-Agent": "arvel-cli"})  # noqa: S310

    try:
        with urlopen(req, timeout=30) as response:  # noqa: S310
            data = response.read()
    except URLError, OSError:
        return None

    import tempfile

    extract_dir = Path(tempfile.mkdtemp(prefix="arvel-new-"))

    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            if ".." in member.name or member.name.startswith("/"):
                continue
            if member.issym() or member.islnk():
                continue
            tar.extract(member, extract_dir, filter="data")

    subdirs = [d for d in extract_dir.iterdir() if d.is_dir()]
    if len(subdirs) == 1:
        return subdirs[0]
    return extract_dir


def _download_skeleton_git_clone(repo_url: str, branch: str) -> Path | None:
    """Fall back to ``git clone --depth 1``. Returns None on failure."""
    import tempfile

    clone_dir = Path(tempfile.mkdtemp(prefix="arvel-new-"))
    target = clone_dir / "skeleton"

    try:
        result = subprocess.run(  # noqa: S603
            ["git", "clone", "--depth", "1", "--branch", branch, repo_url, str(target)],  # noqa: S607
            capture_output=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            # Branch/tag might not exist — retry with default branch
            result = subprocess.run(  # noqa: S603
                ["git", "clone", "--depth", "1", repo_url, str(target)],  # noqa: S607
                capture_output=True,
                timeout=60,
                check=False,
            )
        if result.returncode == 0 and target.is_dir():
            git_dir = target / ".git"
            if git_dir.exists():
                shutil.rmtree(git_dir)
            return target
    except FileNotFoundError, subprocess.TimeoutExpired:
        pass
    return None


def _resolve_latest_tag(owner_repo: str) -> str:
    """Query the GitHub API for the latest release tag."""
    url = f"https://api.github.com/repos/{owner_repo}/releases/latest"
    req = Request(url, headers={"User-Agent": "arvel-cli"})  # noqa: S310

    try:
        with urlopen(req, timeout=15) as response:  # noqa: S310
            data = json.loads(response.read())
            return data["tag_name"]
    except Exception:
        return "main"


_GHA_ESCAPE = "\x00GHA_EXPR\x00"


def render_skeleton(
    *,
    skeleton_dir: Path,
    target_dir: Path,
    context: dict[str, Any],
) -> None:
    """Copy skeleton to target, rendering .j2 files with Jinja2.

    GitHub Actions ``${{ }}`` expressions are escaped before rendering so
    Jinja2 doesn't try to evaluate them.
    """
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(skeleton_dir, target_dir)

    env = Environment(
        loader=FileSystemLoader(str(target_dir)),
        autoescape=False,  # noqa: S701 — rendering Python/config files, not HTML
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    for j2_file in list(target_dir.rglob("*.j2")):
        raw = j2_file.read_text(encoding="utf-8")
        escaped = raw.replace("${{", f"${_GHA_ESCAPE}{{")

        j2_file.write_text(escaped, encoding="utf-8")

        rel = j2_file.relative_to(target_dir)
        template = env.get_template(str(rel))
        rendered = template.render(**context)
        rendered = rendered.replace(f"${_GHA_ESCAPE}{{", "${{")

        output_path = j2_file.with_suffix("")
        output_path.write_text(rendered)
        j2_file.unlink()


def _setup_env(target_dir: Path, context: dict[str, Any]) -> None:
    """Ensure .env exists. Prefer the rendered .env (from .env.j2); fall back to .env.example."""
    env_file = target_dir / ".env"
    if env_file.exists():
        return
    env_example = target_dir / ".env.example"
    if env_example.exists():
        shutil.copy2(env_example, env_file)


def _run_uv_sync(target_dir: Path) -> None:
    """Run uv sync in the project directory."""
    try:
        subprocess.run(
            ["uv", "sync"],  # noqa: S607
            cwd=target_dir,
            check=False,
            capture_output=True,
            timeout=120,
        )
    except FileNotFoundError:
        typer.echo("Warning: uv not found. Run 'uv sync' manually.", err=True)
    except subprocess.TimeoutExpired:
        typer.echo("Warning: uv sync timed out. Run 'uv sync' manually.", err=True)


def _git_init(target_dir: Path) -> None:
    """Initialize a git repo with an initial commit."""
    try:
        subprocess.run(["git", "init"], cwd=target_dir, check=True, capture_output=True)  # noqa: S607
        subprocess.run(["git", "add", "."], cwd=target_dir, check=True, capture_output=True)  # noqa: S607
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],  # noqa: S607
            cwd=target_dir,
            check=True,
            capture_output=True,
        )
    except FileNotFoundError, subprocess.CalledProcessError:
        typer.echo("Warning: git initialization failed.", err=True)


def _validate_choice(option: str, value: str, configs: dict[str, dict[str, str]]) -> None:
    """Validate a CLI option value against its config map."""
    if value not in configs:
        choices = ", ".join(configs)
        typer.echo(f"Unknown {option} '{value}'. Choose: {choices}.")
        raise typer.Exit(code=1)


def _build_context(driver_choices: dict[str, str], package_name: str) -> dict[str, Any]:
    """Build the full Jinja2 template context from driver choices."""
    db_cfg = DATABASE_CONFIGS[driver_choices["database"]]
    arvel_extras = _collect_extras(driver_choices)
    extras_suffix = f"[{','.join(arvel_extras)}]" if arvel_extras else ""

    cache = driver_choices["cache"]
    queue = driver_choices["queue"]
    broadcast_drv = driver_choices["broadcast"]

    use_redis = cache == "redis" or queue in ("redis", "taskiq") or broadcast_drv == "redis"

    return {
        "app_name": package_name,
        "app_name_title": to_pascal_case(package_name),
        "python_version": "3.14",
        "arvel_version": _get_arvel_version(),
        "secret_key": _generate_secret_key(),
        # Database
        "database_driver": db_cfg["driver"],
        "database_sa_driver": db_cfg["sa_driver"],
        "database_url": db_cfg["url_template"].format(app_name=package_name),
        "db_host": db_cfg["db_host"],
        "db_port": db_cfg["db_port"],
        "db_username": db_cfg["db_username"],
        "db_database": db_cfg["db_database"].format(app_name=package_name),
        # Service drivers
        "cache_driver": CACHE_CONFIGS[cache]["driver"],
        "queue_driver": QUEUE_CONFIGS[queue]["driver"],
        "mail_driver": MAIL_CONFIGS[driver_choices["mail"]]["driver"],
        "storage_driver": STORAGE_CONFIGS[driver_choices["storage"]]["driver"],
        "search_driver": SEARCH_CONFIGS[driver_choices["search"]]["driver"],
        "broadcast_driver": BROADCAST_CONFIGS[broadcast_drv]["driver"],
        # Dependency extras
        "arvel_extras": extras_suffix,
        # Docker Compose conditionals
        "use_postgres": driver_choices["database"] == "postgres",
        "use_mysql": driver_choices["database"] == "mysql",
        "use_redis": use_redis,
        "use_smtp": driver_choices["mail"] == "smtp",
        "use_s3": driver_choices["storage"] == "s3",
        "use_meilisearch": driver_choices["search"] == "meilisearch",
        "use_elasticsearch": driver_choices["search"] == "elasticsearch",
    }


@new_app.command(name="project")
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
    if not validate_project_name(name):
        typer.echo("Invalid project name. Use lowercase letters, digits, hyphens, and underscores.")
        raise typer.Exit(code=1)

    target = Path.cwd() / name
    if target.exists() and not force:
        typer.echo(f"Directory '{name}' already exists. Use --force to overwrite.")
        raise typer.Exit(code=1)

    if preset and preset not in PRESETS:
        valid = ", ".join(PRESETS)
        typer.echo(f"Unknown preset '{preset}'. Choose: {valid}.")
        raise typer.Exit(code=1)

    _validate_choice("database", database, DATABASE_CONFIGS)
    _validate_choice("cache", cache, CACHE_CONFIGS)
    _validate_choice("queue", queue, QUEUE_CONFIGS)
    _validate_choice("mail", mail, MAIL_CONFIGS)
    _validate_choice("storage", storage, STORAGE_CONFIGS)
    _validate_choice("search", search, SEARCH_CONFIGS)
    _validate_choice("broadcast", broadcast, BROADCAST_CONFIGS)

    # Resolve driver choices: interactive prompts, preset, or CLI flags
    if no_input:
        base = PRESETS[preset] if preset else PRESETS["minimal"]
        # CLI flags override the preset/defaults
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
        )

    from arvel.cli.app import BANNER

    typer.echo(typer.style(BANNER, fg=typer.colors.CYAN, bold=True))
    typer.echo(f"Creating project '{name}'...")

    if using:
        repo_url = using
    else:
        templates = _fetch_templates_registry()
        repo_url = _resolve_template_repo(templates, template)

    skeleton_dir = _download_skeleton(repo_url, branch)

    package_name = to_package_name(name)
    context = _build_context(driver_choices, package_name)

    render_skeleton(skeleton_dir=skeleton_dir, target_dir=target, context=context)

    _setup_env(target, context)

    if driver_choices["database"] == "sqlite":
        db_dir = target / "database"
        db_dir.mkdir(exist_ok=True)
        (db_dir / "database.sqlite").touch()

    if not no_install:
        typer.echo("Installing dependencies...")
        _run_uv_sync(target)

    if not no_git:
        typer.echo("Initializing git repository...")
        _git_init(target)

    green = typer.colors.GREEN
    dim = typer.colors.BRIGHT_BLACK

    typer.echo()
    typer.echo(
        typer.style("  ✓ Application ready!", fg=green, bold=True) + " Build something amazing."
    )
    typer.echo()
    typer.echo(f"  {typer.style('$', fg=dim)} cd {name}")
    typer.echo(f"  {typer.style('$', fg=dim)} arvel serve")
    typer.echo(f"  {typer.style('$', fg=dim)} arvel make module <your-first-module>")
    typer.echo()
