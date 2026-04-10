"""Seeder framework for database population.

Provides a Seeder base class, directory-based discovery, and a SeedRunner
that enforces production safety and transactional execution.
"""

from __future__ import annotations

import contextlib
import importlib.util
import inspect
import sys
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from arvel.data.transaction import Transaction

from arvel.logging import Log

_logger = Log.named("arvel.data.seeder")


class Seeder(ABC):
    """Base class for database seeders.

    Subclass and implement ``run()`` to populate data::

        class UserSeeder(Seeder):
            async def run(self, tx: Transaction) -> None:
                await tx.users.create({"name": "Admin", "email": "admin@app.com"})
    """

    @abstractmethod
    async def run(self, tx: Transaction) -> None: ...


def _load_seeder_module(py_file: Path) -> list[type[Seeder]]:
    """Load a single seeder file and return any ``Seeder`` subclasses it defines."""
    spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
    if spec is None or spec.loader is None:
        return []

    mod = importlib.util.module_from_spec(spec)
    sys.modules[py_file.stem] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(py_file.stem, None)
        _logger.debug(
            "Skipping seeder module that failed to load: %s",
            py_file,
            exc_info=True,
        )
        return []

    return [
        obj
        for _name, obj in inspect.getmembers(mod, inspect.isclass)
        if issubclass(obj, Seeder) and obj is not Seeder
    ]


def discover_seeders(seeders_dir: Path) -> list[type[Seeder]]:
    """Scan a directory for Seeder subclasses, sorted alphabetically by filename.

    The project root (``seeders_dir.parent.parent``, i.e. two levels up from
    ``database/seeders/``) is temporarily added to ``sys.path`` so that seeder
    modules can use application-level imports such as
    ``from app.models.user import User``.
    """
    if not seeders_dir.is_dir():
        return []

    project_root = str(seeders_dir.parent.parent)
    path_added = project_root not in sys.path
    if path_added:
        sys.path.insert(0, project_root)

    try:
        found: list[type[Seeder]] = []
        for py_file in sorted(seeders_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            found.extend(_load_seeder_module(py_file))
    finally:
        if path_added:
            with contextlib.suppress(ValueError):
                sys.path.remove(project_root)

    return found


class SeedRunner:
    """Discovers and executes seeders with production safety."""

    def __init__(self, *, seeders_dir: Path, db_url: str) -> None:
        self._seeders_dir = seeders_dir
        self._db_url = db_url

    async def run(
        self,
        *,
        environment: str = "development",
        force: bool = False,
        seeder_class: str | None = None,
    ) -> None:
        """Run seeders. Refuses in production without force."""
        if environment == "production" and not force:
            msg = "Refusing to seed in production without --force flag"
            raise RuntimeError(msg)

        seeders = discover_seeders(self._seeders_dir)

        if seeder_class:
            seeders = [s for s in seeders if s.__name__ == seeder_class]

        if not seeders:
            return

        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

        from arvel.data.observer import ObserverRegistry
        from arvel.data.transaction import Transaction

        engine = create_async_engine(self._db_url, echo=False)
        registry = ObserverRegistry()

        try:
            for seeder_cls in seeders:
                async with engine.connect() as conn:
                    trans = await conn.begin()
                    async with AsyncSession(bind=conn, expire_on_commit=False) as session:
                        tx = Transaction(session=session, observer_registry=registry)
                        seeder = seeder_cls()
                        async with tx:
                            await seeder.run(tx)
                        if trans.is_active:
                            await trans.commit()
        finally:
            await engine.dispose()
