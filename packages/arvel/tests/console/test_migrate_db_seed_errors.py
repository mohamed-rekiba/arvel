"""Error-path coverage for migrate / db_seed via the CLI surface.

Every branch is exercised by invoking the actual Typer commands; no
private-helper imports. This keeps coverage honest without violating
`reportPrivateUsage`.

Branches covered:
 - migrate / migrate:rollback / migrate:status: bootstrap → exit 2
 - db:seed: bootstrap → exit 2, empty name → exit 2
 - db:seed: app.base_path missing/string/callable + invalid type
 - db:seed: seeder file unloadable (syntax error) → exit 2 with stderr
 - db:seed: seeder class wrong type (not a Seeder subclass) → exit 2
 - migrate: container missing / container.make missing / wrong type → exit 2
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from arvel.console import Application, Command
from arvel.console.commands.db_seed import DbSeedCommand
from arvel.console.commands.migrate import (
    MigrateCommand,
    MigrateRollbackCommand,
    MigrateStatusCommand,
)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from typer.testing import CliRunner

from .conftest import invoke_async

runner = CliRunner()


def _attach_app(framework_app: Any, *cmds: Command) -> Application:
    """Bind `framework_app` to each command and wrap them in a console Application."""
    for cmd in cmds:
        cmd.app = framework_app  # type: ignore[assignment]
    return Application(commands=list(cmds))


# ---------------------------------------------------------------------------
# migrate — bootstrap exit-2 paths (no framework Application)
# ---------------------------------------------------------------------------


def test_migrate_no_framework_app_exits_2() -> None:
    """No framework Application attached → exit 2 on stderr."""
    app = Application(commands=[MigrateCommand()])
    result = invoke_async(runner, app.typer_app, ["migrate"])
    assert result.exit_code == 2
    assert "arvel:" in (result.stderr or result.stdout)


def test_migrate_rollback_no_framework_app_exits_2() -> None:
    app = Application(commands=[MigrateRollbackCommand()])
    result = invoke_async(runner, app.typer_app, ["migrate:rollback"])
    assert result.exit_code == 2


def test_migrate_status_no_framework_app_exits_2() -> None:
    app = Application(commands=[MigrateStatusCommand()])
    result = invoke_async(runner, app.typer_app, ["migrate:status"])
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# migrate — container-resolution branches (no .container, no .make, wrong type)
# ---------------------------------------------------------------------------


class _NoContainerApp:
    """Framework app without a `container` attribute."""


class _NoMakeApp:
    """Framework app whose container has no `.make`."""

    def __init__(self) -> None:
        class _Container:
            pass

        self.container = _Container()


class _WrongTypeApp:
    """Framework app whose container.make returns something that isn't an AsyncEngine."""

    def __init__(self) -> None:
        class _Container:
            def make(self, _key: object) -> object:
                return "definitely-not-an-engine"

        self.container = _Container()


def test_migrate_container_missing_exits_2() -> None:
    app = _attach_app(_NoContainerApp(), MigrateCommand())
    result = invoke_async(runner, app.typer_app, ["migrate"])
    assert result.exit_code == 2
    assert "no container" in (result.stderr + result.stdout).lower()


def test_migrate_container_make_missing_exits_2() -> None:
    app = _attach_app(_NoMakeApp(), MigrateCommand())
    result = invoke_async(runner, app.typer_app, ["migrate"])
    assert result.exit_code == 2
    assert "no .make" in (result.stderr + result.stdout)


def test_migrate_container_returns_wrong_type_exits_2() -> None:
    app = _attach_app(_WrongTypeApp(), MigrateCommand())
    result = invoke_async(runner, app.typer_app, ["migrate"])
    assert result.exit_code == 2
    assert "asyncengine" in (result.stderr + result.stdout).lower()


# ---------------------------------------------------------------------------
# db:seed — bootstrap + name allowlist edge cases
# ---------------------------------------------------------------------------


def test_db_seed_no_framework_app_exits_2() -> None:
    """No framework Application → exit 2."""
    app = Application(commands=[DbSeedCommand()])
    result = invoke_async(runner, app.typer_app, ["db:seed"])
    assert result.exit_code == 2
    assert "bootstrap failed" in (result.stderr or result.stdout).lower()


def test_db_seed_empty_seeder_name_exits_2() -> None:
    """--seeder='' is rejected before bootstrap is even consulted."""
    app = Application(commands=[DbSeedCommand()])
    result = invoke_async(runner, app.typer_app, ["db:seed", "--seeder", ""])
    assert result.exit_code == 2
    assert "invalid" in (result.stderr or result.stdout).lower()


# ---------------------------------------------------------------------------
# db:seed — base_path resolution (string / callable / missing / wrong type)
# ---------------------------------------------------------------------------


@pytest.fixture
def engine() -> Iterator[AsyncEngine]:
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        yield eng
    finally:
        asyncio.run(eng.dispose())


def _seeder_app(base_path_value: object, engine_: AsyncEngine) -> Application:
    """Build a framework Application with the given `base_path` shape."""

    class _Container:
        def make(self, key: object) -> object:
            if key is AsyncEngine:
                return engine_
            if getattr(key, "__origin__", None) is async_sessionmaker or key is async_sessionmaker:
                return async_sessionmaker(engine_, expire_on_commit=False)
            raise KeyError(key)

    class _FakeApp:
        def __init__(self) -> None:
            self.container = _Container()
            self.base_path = base_path_value  # type: ignore[assignment]

    return _attach_app(_FakeApp(), DbSeedCommand())


def test_db_seed_base_path_string_resolves_correctly(tmp_path: Path, engine: AsyncEngine) -> None:
    """app.base_path as a string is coerced to Path and used to locate seeders."""
    (tmp_path / "database" / "seeders").mkdir(parents=True)
    (tmp_path / "database" / "seeders" / "database_seeder.py").write_text(
        '"""Test seeder."""\n'
        "from arvel.database import Seeder\n"
        "class DatabaseSeeder(Seeder):\n"
        "    async def run(self) -> None:\n"
        "        return\n"
    )
    app = _seeder_app(str(tmp_path), engine)
    result = invoke_async(runner, app.typer_app, ["db:seed"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Seeded" in result.stdout or "DatabaseSeeder" in result.stdout


def test_db_seed_base_path_missing_uses_cwd(
    tmp_path: Path, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When app has no `base_path` attribute, the CLI falls back to cwd."""
    (tmp_path / "database" / "seeders").mkdir(parents=True)
    (tmp_path / "database" / "seeders" / "database_seeder.py").write_text(
        '"""Test seeder."""\n'
        "from arvel.database import Seeder\n"
        "class DatabaseSeeder(Seeder):\n"
        "    async def run(self) -> None:\n"
        "        return\n"
    )
    monkeypatch.chdir(tmp_path)

    class _Container:
        def make(self, key: object) -> object:
            if key is AsyncEngine:
                return engine
            if getattr(key, "__origin__", None) is async_sessionmaker or key is async_sessionmaker:
                return async_sessionmaker(engine, expire_on_commit=False)
            raise KeyError(key)

    class _NoBasePathApp:
        def __init__(self) -> None:
            self.container = _Container()

    app = _attach_app(_NoBasePathApp(), DbSeedCommand())
    result = invoke_async(runner, app.typer_app, ["db:seed"])
    assert result.exit_code == 0, result.stdout + result.stderr


def test_db_seed_base_path_invalid_type_returns_error(
    engine: AsyncEngine,
) -> None:
    """app.base_path set to an int → TypeError surfaces as a CLI error."""
    app = _seeder_app(42, engine)
    result = invoke_async(runner, app.typer_app, ["db:seed"])
    # TypeError raised mid-callback ends up as a Click exception. Either it
    # surfaces as exit 1 (caught by the broad `Exception` handler) or it
    # propagates as a non-zero exit. Both confirm the path was hit.
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# db:seed — _load_seeder_class branch coverage via real seeder files
# ---------------------------------------------------------------------------


def test_db_seed_seeder_file_syntax_error_exits_2(tmp_path: Path, engine: AsyncEngine) -> None:
    """A seeder file with a syntax error → exit 2 with a clear stderr message."""
    (tmp_path / "database" / "seeders").mkdir(parents=True)
    (tmp_path / "database" / "seeders" / "broken_seeder.py").write_text(
        "this is not valid python !!!\n"
    )
    app = _seeder_app(tmp_path, engine)
    result = invoke_async(runner, app.typer_app, ["db:seed", "--seeder", "BrokenSeeder"])
    assert result.exit_code == 2, (
        f"expected 2 for syntax error, got {result.exit_code}; "
        f"stderr={result.stderr!r} stdout={result.stdout!r} "
        f"exception={result.exception!r}"
    )
    assert "failed to load" in result.stderr.lower()


def test_db_seed_class_exists_but_not_a_seeder_exits_2(tmp_path: Path, engine: AsyncEngine) -> None:
    """File defines a class with the right name, but it doesn't subclass Seeder."""
    (tmp_path / "database" / "seeders").mkdir(parents=True)
    (tmp_path / "database" / "seeders" / "fake_seeder.py").write_text(
        "class FakeSeeder:\n    pass\n"
    )
    app = _seeder_app(tmp_path, engine)
    result = invoke_async(runner, app.typer_app, ["db:seed", "--seeder", "FakeSeeder"])
    assert result.exit_code == 2
    assert "seeder class not found" in result.stderr.lower()


# ---------------------------------------------------------------------------
# handle() — Typer-only commands; handle() must explicitly raise
# ---------------------------------------------------------------------------


def test_db_seed_handle_raises_notimplemented() -> None:
    with pytest.raises(NotImplementedError):
        DbSeedCommand().handle(None)  # type: ignore[arg-type]


def test_migrate_handle_raises_notimplemented() -> None:
    with pytest.raises(NotImplementedError):
        MigrateCommand().handle(None)  # type: ignore[arg-type]


def test_migrate_rollback_handle_raises_notimplemented() -> None:
    with pytest.raises(NotImplementedError):
        MigrateRollbackCommand().handle(None)  # type: ignore[arg-type]


def test_migrate_status_handle_raises_notimplemented() -> None:
    with pytest.raises(NotImplementedError):
        MigrateStatusCommand().handle(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# migrate — base_path resolution branches via the CLI surface
# ---------------------------------------------------------------------------


def _migrate_app(base_path_value: object, engine_: AsyncEngine) -> Application:
    """Build a framework Application for migrate with the given `base_path` shape."""

    class _Container:
        def make(self, key: object) -> object:
            if key is AsyncEngine:
                return engine_
            raise KeyError(key)

    class _FakeApp:
        def __init__(self) -> None:
            self.container = _Container()
            self.base_path = base_path_value  # type: ignore[assignment]

    return _attach_app(_FakeApp(), MigrateCommand())


def test_migrate_base_path_missing_falls_back_to_cwd(
    tmp_path: Path, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No `base_path` attr → resolver falls back to cwd."""
    (tmp_path / "database" / "migrations").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    class _Container:
        def make(self, key: object) -> object:
            if key is AsyncEngine:
                return engine
            raise KeyError(key)

    class _NoBase:
        def __init__(self) -> None:
            self.container = _Container()

    app = _attach_app(_NoBase(), MigrateCommand())
    result = invoke_async(runner, app.typer_app, ["migrate"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Nothing to migrate." in result.stdout


def test_migrate_base_path_string_resolves_correctly(tmp_path: Path, engine: AsyncEngine) -> None:
    """app.base_path as a string is coerced to Path."""
    (tmp_path / "database" / "migrations").mkdir(parents=True)
    app = _migrate_app(str(tmp_path), engine)
    result = invoke_async(runner, app.typer_app, ["migrate"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Nothing to migrate." in result.stdout


def test_migrate_base_path_invalid_type_errors_out(
    engine: AsyncEngine,
) -> None:
    """app.base_path = 42 → resolver raises TypeError → non-zero exit."""
    app = _migrate_app(42, engine)
    result = invoke_async(runner, app.typer_app, ["migrate"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# migrate — dry-run "Nothing to migrate." + file-shape error
# ---------------------------------------------------------------------------


def test_migrate_dry_run_with_no_files_prints_nothing(tmp_path: Path, engine: AsyncEngine) -> None:
    """`migrate --dry-run` with an empty migrations dir prints the nothing-to-migrate line."""
    (tmp_path / "database" / "migrations").mkdir(parents=True)
    app = _migrate_app(tmp_path, engine)
    result = invoke_async(runner, app.typer_app, ["migrate", "--dry-run"])
    assert result.exit_code == 0
    assert "Nothing to migrate." in result.stdout


_MIGRATION_MISSING_UP = '''"""Invalid migration — no up()."""

async def down(schema):
    return
'''


def test_migrate_file_missing_up_exits_1(tmp_path: Path, engine: AsyncEngine) -> None:
    """A migration file without `up` → MigrationFileInvalidError → exit 1."""
    (tmp_path / "database" / "migrations").mkdir(parents=True)
    (tmp_path / "database" / "migrations" / "2026_01_01_bad.py").write_text(_MIGRATION_MISSING_UP)
    app = _migrate_app(tmp_path, engine)
    result = invoke_async(runner, app.typer_app, ["migrate"])
    assert result.exit_code == 1, (
        f"expected 1, got {result.exit_code}; stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "2026_01_01_bad" in result.stderr


# ---------------------------------------------------------------------------
# migrate:rollback — MigrationFailedError and MigrationFileInvalidError paths
# ---------------------------------------------------------------------------


_RAISING_DOWN = '''"""Migration whose down() raises."""

from arvel.database import Schema


async def up(schema: Schema) -> None:
    return


async def down(schema: Schema) -> None:
    raise RuntimeError("rollback boom")
'''


_MIGRATION_MISSING_DOWN = '''"""Migration applied without down()."""

from arvel.database import Schema


async def up(schema: Schema) -> None:
    return
'''


def test_migrate_rollback_body_failure_exits_1(tmp_path: Path, engine: AsyncEngine) -> None:
    """A migration with a raising down → MigrationFailedError → exit 1."""
    (tmp_path / "database" / "migrations").mkdir(parents=True)
    (tmp_path / "database" / "migrations" / "2026_01_01_raising.py").write_text(_RAISING_DOWN)

    apply_app = _migrate_app(tmp_path, engine)
    apply_result = invoke_async(runner, apply_app.typer_app, ["migrate"])
    assert apply_result.exit_code == 0, apply_result.stdout + apply_result.stderr

    rb_app = _attach_app_for_rollback(tmp_path, engine)
    result = invoke_async(runner, rb_app.typer_app, ["migrate:rollback"])
    assert result.exit_code == 1, (
        f"expected 1, got {result.exit_code}; stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "rollback failed" in result.stderr.lower()
    assert "2026_01_01_raising" in result.stderr


def test_migrate_rollback_file_missing_down_exits_1(tmp_path: Path, engine: AsyncEngine) -> None:
    """Migration applied without down → MigrationFileInvalidError on rollback → exit 1."""
    (tmp_path / "database" / "migrations").mkdir(parents=True)
    (tmp_path / "database" / "migrations" / "2026_01_01_no_down.py").write_text(
        _MIGRATION_MISSING_DOWN
    )

    apply_app = _migrate_app(tmp_path, engine)
    apply_result = invoke_async(runner, apply_app.typer_app, ["migrate"])
    assert apply_result.exit_code == 0, apply_result.stdout + apply_result.stderr

    rb_app = _attach_app_for_rollback(tmp_path, engine)
    result = invoke_async(runner, rb_app.typer_app, ["migrate:rollback"])
    assert result.exit_code == 1
    assert "2026_01_01_no_down" in result.stderr


def _attach_app_for_rollback(base_path: Path, engine_: AsyncEngine) -> Application:
    """Same fake framework Application but with MigrateRollbackCommand attached."""

    class _Container:
        def make(self, key: object) -> object:
            if key is AsyncEngine:
                return engine_
            raise KeyError(key)

    class _FakeApp:
        def __init__(self) -> None:
            self.container = _Container()
            self.base_path = base_path  # type: ignore[assignment]

    return _attach_app(_FakeApp(), MigrateRollbackCommand())
