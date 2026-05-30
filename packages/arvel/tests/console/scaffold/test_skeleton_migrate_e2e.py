"""End-to-end skeleton boot → ``arvel migrate`` regression.

Guard against the WI-022 escape that motivated ADR-075's auto-baseline rework:

- ``arvel new my-app`` rendered the skeleton with a hand-pruned
  ``bootstrap/providers.py`` that listed only ``HttpServiceProvider``.
- ``arvel migrate`` therefore couldn't resolve ``AsyncEngine`` (no
  ``DatabaseServiceProvider``) and ``ConsoleServiceProvider`` was missing too,
  so provider commands never attached.
- The unit suite passed because ``MigrateCommand`` tests use a fake container.

This test renders the real skeleton, drops a no-op migration into
``database/migrations/``, drives ``bootstrap_framework_application`` exactly
the way the ``arvel`` entrypoint does, and runs the migrator against the bound
``AsyncEngine``. It will fail loudly if any framework-baseline provider goes
missing from the auto-registered chain.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from arvel.console.bootstrap import bootstrap_framework_application
from arvel.console.commands.migrate import build_migrator
from arvel.console.entrypoint import build_app
from typer.testing import CliRunner

# Minimal migration following the framework's module-level ``up`` / ``down``
# contract (see ``arvel.database.migrator._run_user_migration_callable``).
_NOOP_MIGRATION = '''"""End-to-end smoke migration — creates a tiny table the test can verify."""

from __future__ import annotations

from arvel.database import Blueprint, Schema


async def up(schema: type[Schema]) -> None:
    def _smoke(t: Blueprint) -> None:
        t.id()

    schema.create("e2e_smoke", _smoke)


async def down(schema: type[Schema]) -> None:
    schema.drop_if_exists("e2e_smoke")
'''


@pytest.fixture
def rendered_project(tmp_path: Path) -> Iterator[Path]:
    """Render the real packaged skeleton via ``arvel new`` into ``tmp_path/my-app``."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as iso_cwd:
        result = runner.invoke(build_app(), ["new", "my-app", "--no-install"])
        assert result.exit_code == 0, result.stderr
        project_root = Path(iso_cwd) / "my-app"

        # Skeleton ships ``.env.testing`` with sqlite+aiosqlite:///:memory:;
        # promote it to ``.env`` so ArvelSettings picks it up at bootstrap.
        shutil.copyfile(project_root / ".env.testing", project_root / ".env")

        # Drop one migration so the migrator actually has work to do.
        migration = project_root / "database" / "migrations" / "20260520_000000_create_smoke.py"
        migration.write_text(_NOOP_MIGRATION)

        yield project_root


@pytest.fixture(autouse=True)
def isolate_bootstrap_module_cache() -> Iterator[None]:
    """``bootstrap_framework_application`` pins the user's module under a
    fixed ``sys.modules`` key. Wipe it before and after each test so adjacent
    tests don't import each other's stale copy.
    """
    sys.modules.pop("arvel_user_bootstrap_app", None)
    yield
    sys.modules.pop("arvel_user_bootstrap_app", None)


@pytest.fixture(autouse=True)
def restore_cwd() -> Iterator[None]:
    """Tests chdir into the rendered project; restore cwd on exit."""
    original = Path.cwd()
    yield
    os.chdir(original)


def test_rendered_skeleton_bootstraps_and_runs_migrate(rendered_project: Path) -> None:
    """The full chain — render → bootstrap → resolve AsyncEngine → migrate."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncEngine

    os.chdir(rendered_project)

    framework_app = bootstrap_framework_application(rendered_project)
    assert framework_app is not None, "bootstrap_framework_application returned None"

    # Drive the same async boot() path the entrypoint runs.
    asyncio.run(framework_app.boot())

    # Auto-baseline contract: AsyncEngine must be resolvable straight out of
    # the rendered skeleton, with no hand-edits to bootstrap/providers.py.
    engine = framework_app.container.make(AsyncEngine)
    assert isinstance(engine, AsyncEngine)

    # Run the migrator the same way ``arvel migrate`` does.
    migrator = build_migrator(framework_app)

    async def _run_and_verify() -> list[str]:
        await migrator.ensure_table()
        applied = await migrator.upgrade()
        # Sanity: the migration body actually executed against the bound engine.
        async with engine.connect() as conn:
            row = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='e2e_smoke'")
            )
            assert row.scalar_one_or_none() == "e2e_smoke"
        return applied

    applied = asyncio.run(_run_and_verify())
    assert applied == ["20260520_000000_create_smoke"]


def test_rendered_skeleton_writes_to_file_based_sqlite_from_dotenv(tmp_path: Path) -> None:
    """End-to-end regression: ``DB_URL`` in ``.env`` must drive the
    engine onto a real on-disk sqlite file.

    Pre-fix story: ``DbConfig`` ignored ``DB_URL`` entirely (no
    ``connection_url`` field), so the engine silently defaulted to
    ``sqlite+aiosqlite:///:memory:``. ``arvel migrate`` reported
    "Ran 1 migration(s)" but no file ever appeared — the schema lived only in
    process memory and evaporated on exit.

    Lock the contract: render skeleton → override ``.env`` with a file-based
    URL → run the migrator → assert the ``.db`` file is on disk AND contains
    the migrated table.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncEngine

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as iso_cwd:
        result = runner.invoke(build_app(), ["new", "my-app", "--no-install"])
        assert result.exit_code == 0, result.stderr
        project_root = Path(iso_cwd) / "my-app"

        # Use an absolute path inside the isolated filesystem so the assertion
        # below can find the file without depending on the migrator's cwd.
        db_path = project_root / "storage" / "app.db"
        (project_root / ".env").write_text(
            f"APP_NAME=MyApp\n"
            f"APP_ENV=testing\n"
            f"LOG_LEVEL=info\n"
            f"DB_URL=sqlite+aiosqlite:///{db_path}\n"
            f"DB_ECHO=false\n"
        )
        (project_root / "database" / "migrations" / "20260520_000000_create_smoke.py").write_text(
            _NOOP_MIGRATION
        )

        # Sanity: no .db file exists before we run the migrator.
        assert not db_path.exists()

        os.chdir(project_root)
        framework_app = bootstrap_framework_application(project_root)
        assert framework_app is not None
        asyncio.run(framework_app.boot())

        engine = framework_app.container.make(AsyncEngine)
        assert str(engine.url) == f"sqlite+aiosqlite:///{db_path}", (
            "engine URL must reflect DB_URL from .env, not the :memory: default"
        )

        migrator = build_migrator(framework_app)

        async def _run() -> list[str]:
            await migrator.ensure_table()
            return await migrator.upgrade()

        applied = asyncio.run(_run())
        assert applied == ["20260520_000000_create_smoke"]

        # The fix proves itself: the .db file is on disk and carries the table.
        assert db_path.exists(), (
            "DB_URL was ignored — migration ran against an in-memory DB "
            "and left no .db file on disk"
        )

        async def _verify_table_on_disk() -> None:
            async with engine.connect() as conn:
                row = await conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' AND name='e2e_smoke'")
                )
                assert row.scalar_one_or_none() == "e2e_smoke"

        asyncio.run(_verify_table_on_disk())


def test_rendered_skeleton_tinker_binds_active_session_for_active_record(
    rendered_project: Path,
) -> None:
    """End-to-end regression for the ``arvel tinker`` ``NoActiveSessionError`` bug.

    The original failure was: a developer ran ``arvel tinker``, typed
    ``await User.first()``, and got ``NoActiveSessionError`` because
    ``DatabaseServiceProvider`` binds the session-maker but never pushes an
    ``AsyncSession`` onto the ``_ACTIVE_SESSION`` ContextVar — that's done by
    HTTP middleware (per-request) and by test fixtures (per-test) but NEVER
    by the REPL.

    Lock the fix end-to-end:

    1. Render the real packaged skeleton.
    2. Bootstrap the framework Application the way ``arvel`` does.
    3. Build a ``ShellCommand`` namespace (this is what tinker calls before
       launching IPython).
    4. Inside an ``asyncio.run(...)`` coroutine — exactly how IPython
       evaluates each ``await`` cell — call ``get_active_session()`` and use
       it to execute a query against the migrated schema.

    If the ContextVar fails to propagate through asyncio task creation, this
    test catches it instead of the user.
    """
    from arvel.console.bootstrap import bootstrap_framework_application
    from arvel.console.commands.migrate import build_migrator
    from arvel.console.commands.shell import ShellCommand
    from arvel.database.session import get_active_session, get_optional_session
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    os.chdir(rendered_project)

    # Apply the smoke migration so there's a real table the REPL can hit.
    framework_app = bootstrap_framework_application(rendered_project)
    assert framework_app is not None
    asyncio.run(framework_app.boot())
    migrator = build_migrator(framework_app)

    async def _apply_smoke_migration() -> None:
        await migrator.ensure_table()
        await migrator.upgrade()

    asyncio.run(_apply_smoke_migration())

    cmd = ShellCommand()
    cmd.app = framework_app
    try:
        namespace = cmd.build_namespace()
        assert "session" in namespace, namespace.keys()
        assert isinstance(namespace["session"], AsyncSession)

        async def _read_table_through_active_session() -> str | None:
            # IPython's ``using="asyncio"`` evaluates each ``await`` cell via
            # ``asyncio.run`` / ``loop.run_until_complete``. The new task
            # copies the surrounding context, so the ContextVar set in
            # ``build_namespace`` MUST be visible here.
            session = get_active_session()
            result = await session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='e2e_smoke'")
            )
            return result.scalar_one_or_none()

        # ``asyncio.run`` runs the coroutine in a fresh event loop, in a
        # *copied* context. ContextVar propagation is the whole point of
        # the test.
        found = asyncio.run(_read_table_through_active_session())
        assert found == "e2e_smoke"
    finally:
        cmd.release_active_session()
        # And the cleanup contract is enforced too — the next test must see
        # an empty ContextVar.
        assert get_optional_session() is None


def test_rendered_skeleton_binds_console_application(rendered_project: Path) -> None:
    """``ConsoleServiceProvider`` auto-registers so ``_attach_provider_commands``
    can resolve the console ``Application`` and merge provider commands.

    Pre-fix this raised ``BindingResolutionError`` (visible in the original
    ``arvel migrate`` traceback as
    ``ConsoleServiceProvider not bound; provider commands unavailable``) and
    every provider-supplied command — schedule:list, schedule:work, queue:* —
    silently disappeared from the CLI. Resolving the Application + finding at
    least one provider-attached command is enough to lock the invariant.
    """
    from arvel.console import Application as ConsoleApplication

    os.chdir(rendered_project)

    framework_app = bootstrap_framework_application(rendered_project)
    assert framework_app is not None
    asyncio.run(framework_app.boot())

    console_app = framework_app.container.make(ConsoleApplication)
    assert isinstance(console_app, ConsoleApplication)

    # The console Application built by ConsoleServiceProvider.boot() carries
    # every provider-supplied command. SchedulerServiceProvider sits in the
    # baseline head, so its commands MUST appear here — their absence means
    # the boot pass skipped this provider, which is the exact failure mode
    # the auto-baseline is meant to prevent.
    command_names = {cmd.name for cmd in console_app.iter_commands()}
    assert "schedule:list" in command_names, command_names
    assert "schedule:work" in command_names, command_names
