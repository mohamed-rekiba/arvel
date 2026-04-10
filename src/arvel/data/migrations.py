"""Alembic programmatic wrapper for Arvel migrations.

Wraps alembic.command behind a MigrationRunner class that loads
DatabaseSettings and ArvelModel.metadata automatically.

``run_alembic_env()`` inspects the dialect in the configured URL and
dispatches accordingly:
- **Async dialect** (``asyncpg``, ``asyncmy``, ``aiosqlite``)
  — ``async_engine_from_config`` inside ``asyncio.run()``.
- **Sync dialect** (``sqlite``, ``pymysql``, etc.)
  — plain ``create_engine``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from types import ModuleType

    from sqlalchemy import Connection, MetaData

from alembic import command as alembic_cmd
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError

from arvel.data.model import ArvelModel


class MigrationStatusEntry(TypedDict):
    """Structured migration status entry."""

    revision: str
    message: str | None
    down_revision: str | list[str] | tuple[str, ...] | None


# ── Framework migration registry ────────────────────────────

_FRAMEWORK_MIGRATIONS: list[tuple[str, str]] = []


def register_framework_migration(filename: str, content: str) -> None:
    """Register a migration that ships with the framework.

    Called by framework providers (e.g. MediaProvider) at import time.
    The migration is published into the user's ``database/migrations/``
    directory when ``MigrationRunner.upgrade()`` or ``fresh()`` runs,
    but only if a file with the same base name doesn't already exist.
    """
    _FRAMEWORK_MIGRATIONS.append((filename, content))


class PublishResult:
    """Outcome of a single framework migration publish attempt."""

    __slots__ = ("action", "filename")

    def __init__(self, filename: str, action: str) -> None:
        self.filename = filename
        self.action = action  # "published", "skipped", "overwritten"


def publish_framework_migrations(
    migrations_dir: Path,
    *,
    force: bool = False,
) -> list[PublishResult]:
    """Copy registered framework migrations into *migrations_dir*.

    By default, a migration is skipped when the target directory already
    contains a file whose stem suffix matches (e.g. ``*_create_media_table``).
    Pass *force=True* to overwrite existing files.

    Returns a list of :class:`PublishResult` objects describing what happened
    for each registered migration.
    """
    migrations_dir.mkdir(parents=True, exist_ok=True)
    existing_stems = {
        f.stem.split("_", 1)[-1] if "_" in f.stem else f.stem
        for f in migrations_dir.iterdir()
        if f.suffix == ".py" and f.name[0].isdigit()
    }

    results: list[PublishResult] = []
    for filename, content in _FRAMEWORK_MIGRATIONS:
        stem = filename.rsplit(".", 1)[0]
        tag = stem.split("_", 1)[-1] if "_" in stem else stem
        target = migrations_dir / filename

        if tag in existing_stems and not force:
            results.append(PublishResult(filename, "skipped"))
            continue

        action = "overwritten" if target.exists() else "published"
        target.write_text(content)
        results.append(PublishResult(filename, action))

    return results


_ARVEL_REVISION_BY_PATH: dict[Path, tuple[str, str | None]] | None = None
_ARVEL_LOAD_MODULE_PATCHED: bool = False

_ENV_TEMPLATE = """\
from arvel.data.migrations import run_alembic_env

run_alembic_env()
"""


_ASYNC_DIALECT_MARKERS = ("asyncpg", "aiosqlite", "asyncmy", "aiomysql")


def _is_async_url(url: str) -> bool:
    """Return True when *url* uses an async SA dialect."""
    return any(marker in url for marker in _ASYNC_DIALECT_MARKERS)


def run_alembic_env() -> None:
    """Run Alembic env logic using framework-managed defaults.

    Starter/local migration env.py files call this so they don't need
    to import Alembic or SQLAlchemy directly.
    """
    import asyncio
    from logging.config import fileConfig

    from alembic import context
    from sqlalchemy import create_engine, pool
    from sqlalchemy.ext.asyncio import async_engine_from_config

    config = context.config

    if config.config_file_name is not None:
        fileConfig(config.config_file_name)

    target_metadata = ArvelModel.metadata
    inject_revisions(config.get_main_option("script_location") or ".")

    url = config.get_main_option("sqlalchemy.url") or ""

    def run_migrations_offline() -> None:
        context.configure(
            url=url,
            target_metadata=target_metadata,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
        )
        with context.begin_transaction():
            context.run_migrations()

    def do_run_migrations(connection: Connection) -> None:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

    def run_sync_migrations() -> None:
        if not url:
            msg = "Missing sqlalchemy.url in Alembic config"
            raise RuntimeError(msg)
        connectable = create_engine(url, poolclass=pool.NullPool)
        with connectable.connect() as connection:
            do_run_migrations(connection)
        connectable.dispose()

    async def run_async_migrations() -> None:
        connectable = async_engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
        await connectable.dispose()

    if context.is_offline_mode():
        run_migrations_offline()
        return

    if _is_async_url(url):
        asyncio.run(run_async_migrations())
    else:
        run_sync_migrations()


def _discover_migrations(migrations_dir: Path) -> list[Path]:
    """Return migration files sorted by timestamp filename.

    Scans the root migrations directory directly (Laravel convention),
    not a ``versions/`` subdirectory.
    """
    results: list[Path] = []
    if not migrations_dir.is_dir():
        return results
    for f in sorted(migrations_dir.iterdir()):
        if f.is_file() and f.suffix == ".py" and f.name[0].isdigit():
            results.append(f)
    return results


def _revision_id_from_filename(path: Path) -> str:
    """Derive a stable revision ID from the filename."""
    return path.stem.replace("_", "")[:12]


def inject_revisions(migrations_dir: str | Path) -> None:
    """Dynamically set revision/down_revision on migration modules.

    Called from env.py before Alembic runs. Builds a revision chain from
    sorted migration filenames, then patches Alembic's module loader so each
    file receives ``revision`` / ``down_revision`` when loaded (matching
    Alembic's own load path and module identity).
    """
    global _ARVEL_REVISION_BY_PATH, _ARVEL_LOAD_MODULE_PATCHED

    import alembic.util.pyfiles as pyfiles

    mdir = Path(migrations_dir)
    vdir = mdir / "versions"
    scan_dir = vdir if vdir.is_dir() else mdir
    if not scan_dir.is_dir():
        _ARVEL_REVISION_BY_PATH = {}
        return

    files = _discover_migrations(scan_dir)
    prev_rev: str | None = None
    by_path: dict[Path, tuple[str, str | None]] = {}
    for f in files:
        rev = _revision_id_from_filename(f)
        by_path[f.resolve()] = (rev, prev_rev)
        prev_rev = rev

    _ARVEL_REVISION_BY_PATH = by_path

    if _ARVEL_LOAD_MODULE_PATCHED:
        return

    _orig = pyfiles.load_module_py

    def _wrapped(module_id: str, path: str | Path) -> ModuleType:
        mod = _orig(module_id, path)
        if _ARVEL_REVISION_BY_PATH:
            key = Path(path).resolve()
            meta = _ARVEL_REVISION_BY_PATH.get(key)
            if meta is not None:
                rev_id, down_id = meta
                mod.revision = rev_id  # ty: ignore[unresolved-attribute]
                mod.down_revision = down_id  # ty: ignore[unresolved-attribute]
                mod.branch_labels = None  # ty: ignore[unresolved-attribute]
                mod.depends_on = None  # ty: ignore[unresolved-attribute]
        return mod

    _ARVEL_LOAD_MODULE_PATCHED = True
    pyfiles.load_module_py = _wrapped  # ty: ignore[invalid-assignment]


class MigrationRunner:
    """Programmatic Alembic migration runner.

    Wraps alembic.command operations behind an async-friendly interface.
    Uses ArvelModel.metadata for auto-generation and reads DB URL from
    the caller (typically DatabaseSettings).

    The original DB URL (async or sync dialect) is passed through to
    ``run_alembic_env()`` which dispatches the correct engine strategy.
    """

    def __init__(self, *, db_url: str, migrations_dir: str) -> None:
        self._db_url = db_url
        self._migrations_dir = Path(migrations_dir)
        self._is_sqlite = "sqlite" in db_url
        self._ensure_env()

    @property
    def target_metadata(self) -> MetaData:
        return ArvelModel.metadata

    def _build_config(self) -> AlembicConfig:
        cfg = AlembicConfig()
        cfg.set_main_option("script_location", str(self._migrations_dir))
        cfg.set_main_option("sqlalchemy.url", self._db_url)
        return cfg

    def _ensure_env(self) -> None:
        """Write env.py if it doesn't exist."""
        self._migrations_dir.mkdir(parents=True, exist_ok=True)
        (self._migrations_dir / "versions").mkdir(exist_ok=True)

        env_path = self._migrations_dir / "env.py"
        if not env_path.exists():
            env_path.write_text(_ENV_TEMPLATE)

    def _sync_versions(self) -> None:
        """Mirror root-level migration files into ``versions/`` for Alembic.

        Laravel convention puts migration files directly in the migrations
        directory. Alembic expects them in a ``versions/`` subdirectory.
        This method symlinks root-level migration .py files into ``versions/``
        so both conventions coexist.
        """
        versions_dir = self._migrations_dir / "versions"
        versions_dir.mkdir(exist_ok=True)

        for existing in versions_dir.iterdir():
            if existing.is_symlink():
                existing.unlink()

        for f in _discover_migrations(self._migrations_dir):
            link = versions_dir / f.name
            if not link.exists():
                link.symlink_to(f.resolve())

    def generate(self, message: str) -> str:
        """Generate a new migration file from a Jinja template."""
        from datetime import UTC, datetime

        from arvel.cli.templates.engine import render_template

        timestamp = datetime.now(UTC).strftime("%Y_%m_%d_%H%M%S")
        slug = message.lower().replace(" ", "_")
        filename = f"{timestamp}_{slug}.py"

        table_name = self._extract_table_name(message)

        content = render_template(
            "migration.py.j2",
            {"message": message, "table_name": table_name},
        )

        filepath = self._migrations_dir / filename
        filepath.write_text(content)
        return str(filepath)

    @staticmethod
    def _extract_table_name(message: str) -> str:
        """Derive table name from migration message.

        'create_users_table' -> 'users'
        'create users table' -> 'users'
        'add_posts_table' -> 'posts'
        """
        normalized = message.lower().replace(" ", "_")
        normalized = normalized.removeprefix("create_")
        normalized = normalized.removeprefix("add_")
        normalized = normalized.removesuffix("_table")
        return normalized

    async def upgrade(
        self,
        revision: str = "head",
        *,
        environment: str = "development",
        force: bool = False,
    ) -> None:
        """Run pending migrations up to revision."""
        self._check_production(environment, force)
        self._sync_versions()
        inject_revisions(self._migrations_dir)
        cfg = self._build_config()
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, alembic_cmd.upgrade, cfg, revision)

    async def downgrade(
        self,
        steps: int = 1,
        *,
        environment: str = "development",
        force: bool = False,
    ) -> None:
        """Rollback N migration steps. Silently succeeds if there are no migrations to rollback."""
        self._check_production(environment, force)
        self._sync_versions()
        inject_revisions(self._migrations_dir)
        cfg = self._build_config()
        target = f"-{steps}"
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, alembic_cmd.downgrade, cfg, target)
        except CommandError:
            pass

    async def fresh(
        self,
        *,
        environment: str = "development",
        force: bool = False,
    ) -> None:
        """Drop **all** tables then re-run all migrations from scratch.

        Unlike ``downgrade`` (which replays downgrade scripts), this method
        uses ``metadata.drop_all()`` to unconditionally drop every known
        table — including the Alembic version table — so the database is
        truly empty before ``upgrade`` runs.  This matches Laravel's
        ``migrate:fresh`` semantics.
        """
        self._check_production(environment, force)
        self._sync_versions()
        inject_revisions(self._migrations_dir)

        await self._drop_all_tables()

        cfg = self._build_config()
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, alembic_cmd.upgrade, cfg, "head")

    async def _drop_all_tables(self) -> None:
        """Drop every table in the database via live introspection.

        Reflects the actual schema from the database rather than relying on
        ``ArvelModel.metadata`` (which may be empty if models haven't been
        imported).  Also drops the Alembic version tracking table so
        ``upgrade`` starts fresh.
        """
        from sqlalchemy import MetaData, text

        def _reflect_and_drop(connection: Connection) -> None:
            reflected = MetaData()
            reflected.reflect(bind=connection)
            reflected.drop_all(bind=connection)
            connection.execute(text("DROP TABLE IF EXISTS alembic_version"))

        if _is_async_url(self._db_url):
            from sqlalchemy.ext.asyncio import create_async_engine

            engine = create_async_engine(self._db_url)
            async with engine.begin() as conn:
                await conn.run_sync(_reflect_and_drop)
            await engine.dispose()
        else:
            from sqlalchemy import create_engine

            engine = create_engine(self._db_url)
            with engine.begin() as conn:
                _reflect_and_drop(conn)
            engine.dispose()

    async def status(self) -> list[MigrationStatusEntry]:
        """Return a list of migration entries with applied/pending status."""
        self._sync_versions()
        inject_revisions(self._migrations_dir)
        cfg = self._build_config()
        script_dir = ScriptDirectory.from_config(cfg)
        result: list[MigrationStatusEntry] = []
        for sc in script_dir.walk_revisions():
            result.append(
                MigrationStatusEntry(
                    revision=sc.revision,
                    message=sc.doc,
                    down_revision=sc.down_revision,
                )
            )
        return result

    @staticmethod
    def get_env_template() -> str:
        """Return the async env.py template string."""
        return _ENV_TEMPLATE

    @staticmethod
    def _check_production(environment: str, force: bool) -> None:
        if environment == "production" and not force:
            msg = "Refusing to run in production without --force flag"
            raise RuntimeError(msg)
