"""Scaffold rendering and environment setup for `arvel new`."""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING, Any

import typer

if TYPE_CHECKING:
    from pathlib import Path

from .config import (
    _VALID_CHOICES,
    BROADCAST_CONFIGS,
    CACHE_CONFIGS,
    DATABASE_CONFIGS,
    MAIL_CONFIGS,
    QUEUE_CONFIGS,
    SEARCH_CONFIGS,
    STORAGE_CONFIGS,
)


def _collect_extras(choices: dict[str, str]) -> list[str]:
    """Gather deduplicated pip extras from the chosen drivers."""
    extras: set[str] = set()
    for option_name, chosen_value in choices.items():
        configs = _VALID_CHOICES[option_name]
        cfg = configs[chosen_value]
        extra = cfg.get("extra", "")
        if extra:
            extras.add(extra)
    return sorted(extras)


_GHA_ESCAPE = "\x00GHA_EXPR\x00"


def render_skeleton(
    *,
    skeleton_dir: Path,
    target_dir: Path,
    context: dict[str, Any],
) -> None:
    """Copy skeleton to target, render .j2 files. GHA ${{ }} expressions are escaped."""
    import shutil

    from jinja2 import Environment, FileSystemLoader

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
    """Ensure .env exists — prefer rendered .env.j2, fall back to .env.example."""
    import shutil

    env_file = target_dir / ".env"
    if env_file.exists():
        return
    env_example = target_dir / ".env.example"
    if env_example.exists():
        shutil.copy2(env_example, env_file)


def _run_uv_sync(target_dir: Path) -> None:
    """Install deps with uv sync. Warns if uv is missing or times out."""
    import subprocess

    try:
        subprocess.run(
            ["uv", "sync", "--all-extras"],  # noqa: S607
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
    """git init + 'Initial commit'. Warns on failure."""
    import subprocess

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


def _build_context(driver_choices: dict[str, str], package_name: str) -> dict[str, Any]:
    """Assemble the Jinja2 template context from driver choices."""
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
        "db_password": db_cfg["db_password"].format(app_name=package_name),
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


def to_package_name(name: str) -> str:
    """Kebab-case to snake_case Python package name."""
    return name.replace("-", "_").lower()


def to_pascal_case(name: str) -> str:
    """snake_case / kebab-case to PascalCase."""
    parts = name.replace("-", "_").split("_")
    return "".join(p.capitalize() for p in parts)


def _generate_secret_key() -> str:
    """64-char hex secret for APP_KEY."""
    return secrets.token_hex(32)


def _get_arvel_version() -> str:
    """Current installed arvel version, or '0.0.0' as fallback."""
    try:
        from importlib.metadata import version

        return version("arvel")
    except Exception:
        return "0.0.0"
