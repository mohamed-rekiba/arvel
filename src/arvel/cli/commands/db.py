"""Database commands — migrate, rollback, fresh, seed, status, publish."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from arvel.data.config import DatabaseSettings

import typer

db_app = typer.Typer(name="db", help="Database migration and seeding commands.")


def _run_db_operation(coro_fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """Run an async DB operation, printing friendly errors instead of tracebacks."""
    try:
        asyncio.run(coro_fn(*args, **kwargs))
    except Exception as exc:
        msg = _friendly_db_error(exc)
        if msg:
            typer.secho(f"Error: {msg}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1) from None
        raise


def _friendly_db_error(exc: Exception) -> str | None:
    """Human-friendly message for known DB errors, or None."""
    name = type(exc).__name__
    text = str(exc)

    if "InvalidPasswordError" in name or "password authentication failed" in text:
        return f"Database authentication failed — check DB_PASSWORD. ({text})"

    if "ConnectionRefusedError" in name or "Connect call failed" in text:
        return "Cannot connect to the database server — is it running?"

    if name in {"OperationalError", "InterfaceError"} or "could not connect" in text.lower():
        return f"Database connection error: {text}"

    if "production" in text.lower() and "force" in text.lower():
        return text

    return None


def _get_settings() -> DatabaseSettings:
    from arvel.data.config import DatabaseSettings
    from arvel.foundation.config import resolve_env_files, with_env_files

    env_files = resolve_env_files(Path.cwd())
    return with_env_files(DatabaseSettings, env_files)


def _migrations_dir() -> str:
    return str(Path.cwd() / "database" / "migrations")


@db_app.command()
def migrate(
    revision: str = typer.Option("head", help="Target revision."),
    force: bool = typer.Option(False, "--force", help="Allow in production."),
) -> None:
    """Run pending database migrations."""
    from arvel.data.migrations import MigrationRunner

    settings = _get_settings()
    runner = MigrationRunner(db_url=settings.url, migrations_dir=_migrations_dir())
    env = "production" if force else "development"
    _run_db_operation(runner.upgrade, revision=revision, environment=env, force=force)
    typer.echo("Migrations applied.")


@db_app.command()
def rollback(
    steps: int = typer.Option(1, "--steps", help="Number of steps to rollback."),
    force: bool = typer.Option(False, "--force", help="Allow in production."),
) -> None:
    """Rollback the last N migration steps."""
    from arvel.data.migrations import MigrationRunner

    settings = _get_settings()
    runner = MigrationRunner(db_url=settings.url, migrations_dir=_migrations_dir())
    env = "production" if force else "development"
    _run_db_operation(runner.downgrade, steps=steps, environment=env, force=force)
    typer.echo(f"Rolled back {steps} step(s).")


@db_app.command()
def fresh(
    force: bool = typer.Option(False, "--force", help="Allow in production."),
) -> None:
    """Drop all tables and re-run all migrations."""
    from arvel.data.migrations import MigrationRunner

    settings = _get_settings()
    runner = MigrationRunner(db_url=settings.url, migrations_dir=_migrations_dir())
    env = "production" if force else "development"
    _run_db_operation(runner.fresh, environment=env, force=force)
    typer.echo("Database refreshed.")


@db_app.command()
def status() -> None:
    """Show migration status."""
    from arvel.data.migrations import MigrationRunner

    settings = _get_settings()
    runner = MigrationRunner(db_url=settings.url, migrations_dir=_migrations_dir())
    entries = asyncio.run(runner.status())
    if not entries:
        typer.echo("No migrations found.")
        return
    for entry in entries:
        typer.echo(f"  {entry['revision']}: {entry['message']}")


@db_app.command()
def seed(
    seeder_class: str | None = typer.Option(None, "--class", help="Run a specific seeder."),
    force: bool = typer.Option(False, "--force", help="Allow in production."),
) -> None:
    """Seed the database."""
    from arvel.data.seeder import SeedRunner

    settings = _get_settings()
    seeders_dir = Path.cwd() / "database" / "seeders"
    runner = SeedRunner(seeders_dir=seeders_dir, db_url=settings.url)
    env = "production" if force else "development"
    _run_db_operation(runner.run, environment=env, force=force, seeder_class=seeder_class)
    typer.echo("Seeding complete.")


@db_app.command()
def publish(
    force: bool = typer.Option(False, "--force", help="Overwrite existing migration files."),
) -> None:
    """Copy framework migrations into the project. Skips existing unless --force."""
    from arvel.data.migrations import publish_framework_migrations

    _ensure_framework_migrations_registered()

    target = Path.cwd() / "database" / "migrations"
    results = publish_framework_migrations(target, force=force)

    if not results:
        typer.echo("No framework migrations registered.")
        return

    published = 0
    for r in results:
        if r.action == "published":
            typer.secho(f"  Published: {r.filename}", fg=typer.colors.GREEN)
            published += 1
        elif r.action == "overwritten":
            typer.secho(f"  Overwritten: {r.filename}", fg=typer.colors.YELLOW)
            published += 1
        else:
            typer.echo(f"  Skipped:   {r.filename}")

    if published:
        typer.echo(f"\n{published} migration(s) published to {target}.")
    else:
        typer.echo("\nAll framework migrations already present — nothing to publish.")


def _ensure_framework_migrations_registered() -> None:
    """Import framework modules so their migrations get registered before publish."""
    import arvel.activity
    import arvel.audit
    import arvel.auth
    import arvel.media.migration
    import arvel.notifications  # noqa: F401
