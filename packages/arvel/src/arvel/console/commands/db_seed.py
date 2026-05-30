"""db:seed command.

Resolves a ``*Seeder`` class from ``database/seeders/<snake>.py`` relative to
the framework Application's base path, binds an ``AsyncSession`` via
``use_session``, then ``await``s ``seeder.run()``.

Exit codes:
- 0 — success
- 1 — seeder body raised
- 2 — bootstrap failed, seeder file missing, seeder class missing,
       or seeder name violates the allowlist
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Annotated, Any, ClassVar

import typer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arvel.console import Command, Context
from arvel.console import _async as _arvel_async
from arvel.console._t import Option as _Option
from arvel.database import Seeder
from arvel.database.session import use_session
from arvel.support.str import Str

_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _validate_seeder_name(name: str) -> str | None:
    """Return None if ``name`` is safe to use in a filename and class lookup."""
    if not name:
        return "Seeder name must not be empty."
    if not _NAME_PATTERN.match(name):
        return (
            "Seeder name must match ^[A-Za-z][A-Za-z0-9_]*$ "
            "(letters, digits, underscore; must start with a letter)."
        )
    return None


def _resolve_base_path(app: object) -> Path:
    base_path = getattr(app, "base_path", None)
    if base_path is None:
        return Path.cwd()
    if callable(base_path):
        return _coerce_to_path(base_path())
    return _coerce_to_path(base_path)


def _coerce_to_path(value: object) -> Path:
    if isinstance(value, Path):
        return value
    if isinstance(value, str):
        return Path(value)
    raise TypeError(f"base_path must be a str or pathlib.Path, got {type(value).__name__}")


def _load_seeder_class(path: Path, class_name: str) -> type[Seeder]:
    """Import the seeder module and return its named class."""
    module_name = f"_arvel_seeder_{path.stem}_{id(path)}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(f"seeder file not found: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise

    cls = getattr(module, class_name, None)
    if cls is None or not isinstance(cls, type) or not issubclass(cls, Seeder):
        raise AttributeError(f"seeder class not found in {path}: {class_name}")
    return cls


async def run_seeder_for_app(app: object, seeder_name: str = "DatabaseSeeder") -> None:
    """Load *seeder_name* from the app's seeders directory and run it.

    Reuses the same session + commit lifecycle as the interactive ``db:seed``
    command. Called by ``migrate:fresh --seed`` and ``migrate:refresh --seed``.
    """
    error = _validate_seeder_name(seeder_name)
    if error is not None:
        raise ValueError(f"invalid seeder name: {error}")

    base = _resolve_base_path(app)
    seeder_path = base / "database" / "seeders" / f"{Str.snake(seeder_name)}.py"
    if not seeder_path.is_file():
        raise FileNotFoundError(f"seeder file not found: {seeder_path}")

    cls = _load_seeder_class(seeder_path, seeder_name)

    _app: Any = app
    maker: async_sessionmaker[AsyncSession] = _app.container.make(async_sessionmaker[AsyncSession])
    async with maker() as session, use_session(session):
        instance = cls()
        try:
            await instance.run()
        except Exception as exc:
            typer.echo(
                f"arvel: seeder failed: {seeder_name} — {type(exc).__name__}: {exc}",
                err=True,
            )
            raise typer.Exit(code=1) from exc
        await session.commit()

    typer.echo(f"Seeded: {seeder_name}")


class DbSeedCommand(Command):
    name: ClassVar[str] = "db:seed"
    help: ClassVar[str] = "Run database seeders"
    needs_application: ClassVar[bool] = True

    def register(self, app: typer.Typer) -> None:
        cmd_self = self

        def _callback(
            seeder: Annotated[
                str, _Option("--seeder", help="Seeder class name")
            ] = "DatabaseSeeder",
        ) -> None:
            error = _validate_seeder_name(seeder)
            if error is not None:
                typer.echo(f"arvel: invalid --seeder: {error}", err=True)
                raise typer.Exit(code=2)

            if cmd_self.app is None:
                typer.echo(
                    "arvel: bootstrap failed: DbSeedCommand needs a framework Application.",
                    err=True,
                )
                raise typer.Exit(code=2)

            base = _resolve_base_path(cmd_self.app)
            seeder_path = base / "database" / "seeders" / f"{Str.snake(seeder)}.py"
            if not seeder_path.is_file():
                typer.echo(f"arvel: seeder file not found: {seeder_path}", err=True)
                raise typer.Exit(code=2)

            try:
                cls = _load_seeder_class(seeder_path, seeder)
            except AttributeError as exc:
                typer.echo(f"arvel: {exc}", err=True)
                raise typer.Exit(code=2) from exc
            except (SyntaxError, ImportError, OSError) as exc:
                typer.echo(
                    f"arvel: seeder file failed to load: {seeder_path} — "
                    f"{type(exc).__name__}: {exc}",
                    err=True,
                )
                raise typer.Exit(code=2) from exc

            _arvel_async.schedule_async(cmd_self._run_seeder(cls, seeder))

        app.command(name=self.name, help=self.help)(_callback)

    def handle(self, ctx: Context) -> int:
        raise NotImplementedError

    async def _run_seeder(self, cls: type[Seeder], seeder_name: str) -> None:
        """Run *cls* inside a bound session; commit on success."""
        if self.app is None:
            raise RuntimeError("DbSeedCommand._run_seeder requires a bound Application")

        maker: async_sessionmaker[AsyncSession] = self.app.container.make(
            async_sessionmaker[AsyncSession]
        )
        async with maker() as session, use_session(session):
            instance = cls()
            try:
                await instance.run()
            except Exception as exc:
                typer.echo(
                    f"arvel: seeder failed: {seeder_name} — {type(exc).__name__}: {exc}",
                    err=True,
                )
                raise typer.Exit(code=1) from exc
            await session.commit()

        typer.echo(f"Seeded: {seeder_name}")
