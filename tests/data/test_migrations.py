"""Tests for Story 6: Database Migrations (Alembic Integration).

Covers: FR-01 through FR-10, NFR-01, SEC-01.
All tests should FAIL until implementation exists.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def migrations_dir(tmp_path: Path) -> Path:
    """Create a temp database/migrations directory."""
    d = tmp_path / "database" / "migrations" / "versions"
    d.mkdir(parents=True)
    return tmp_path / "database" / "migrations"


@pytest.fixture
def db_dir(tmp_path: Path) -> Path:
    """Create a temp database directory."""
    d = tmp_path / "database"
    d.mkdir(parents=True, exist_ok=True)
    return d


class TestMigrationRunnerInit:
    """FR-08: MigrationRunner uses ArvelModel.metadata and DatabaseSettings."""

    def test_migration_runner_importable(self) -> None:
        from arvel.data.migrations import MigrationRunner

        assert MigrationRunner is not None

    def test_migration_runner_accepts_db_url(self, tmp_path: Path) -> None:
        from arvel.data.migrations import MigrationRunner

        runner = MigrationRunner(
            db_url="sqlite+aiosqlite:///test.db",
            migrations_dir=str(tmp_path / "database" / "migrations"),
        )
        assert runner is not None

    def test_migration_runner_uses_arvel_metadata(self, tmp_path: Path) -> None:
        from arvel.data.migrations import MigrationRunner
        from arvel.data.model import ArvelModel

        runner = MigrationRunner(
            db_url="sqlite+aiosqlite:///test.db",
            migrations_dir=str(tmp_path / "database" / "migrations"),
        )
        assert runner.target_metadata is ArvelModel.metadata


class TestMakeMigration:
    """FR-01, FR-02: make:migration generates timestamped migration files."""

    def test_generate_creates_file(self, db_dir: Path) -> None:
        from arvel.data.migrations import MigrationRunner

        migrations_path = db_dir / "migrations"
        migrations_path.mkdir(exist_ok=True)
        (migrations_path / "versions").mkdir(exist_ok=True)

        runner = MigrationRunner(
            db_url="sqlite+aiosqlite:///test.db",
            migrations_dir=str(migrations_path),
        )
        result_path = runner.generate("create_users_table")
        assert result_path is not None
        assert Path(result_path).exists()

    def test_generated_file_has_upgrade_and_downgrade(self, db_dir: Path) -> None:
        from arvel.data.migrations import MigrationRunner

        migrations_path = db_dir / "migrations"
        migrations_path.mkdir(exist_ok=True)
        (migrations_path / "versions").mkdir(exist_ok=True)

        runner = MigrationRunner(
            db_url="sqlite+aiosqlite:///test.db",
            migrations_dir=str(migrations_path),
        )
        result_path = runner.generate("create_posts_table")
        content = Path(result_path).read_text()
        assert "def upgrade()" in content
        assert "def downgrade()" in content


class TestMigrate:
    """FR-03: arvel migrate executes pending migrations."""

    async def test_upgrade_runs_pending(self, db_dir: Path, anyio_backend: str) -> None:
        from arvel.data.migrations import MigrationRunner

        migrations_path = db_dir / "migrations"
        migrations_path.mkdir(exist_ok=True)
        (migrations_path / "versions").mkdir(exist_ok=True)

        runner = MigrationRunner(
            db_url=f"sqlite+aiosqlite:///{db_dir / 'test.db'}",
            migrations_dir=str(migrations_path),
        )
        await runner.upgrade()

    async def test_upgrade_to_specific_revision(self, db_dir: Path, anyio_backend: str) -> None:
        from arvel.data.migrations import MigrationRunner

        migrations_path = db_dir / "migrations"
        migrations_path.mkdir(exist_ok=True)
        (migrations_path / "versions").mkdir(exist_ok=True)

        runner = MigrationRunner(
            db_url=f"sqlite+aiosqlite:///{db_dir / 'test.db'}",
            migrations_dir=str(migrations_path),
        )
        await runner.upgrade(revision="head")


class TestMigrateRollback:
    """FR-04, FR-05: rollback reverts migration steps."""

    async def test_rollback_one_step(self, db_dir: Path, anyio_backend: str) -> None:
        from arvel.data.migrations import MigrationRunner

        migrations_path = db_dir / "migrations"
        migrations_path.mkdir(exist_ok=True)
        (migrations_path / "versions").mkdir(exist_ok=True)

        runner = MigrationRunner(
            db_url=f"sqlite+aiosqlite:///{db_dir / 'test.db'}",
            migrations_dir=str(migrations_path),
        )
        await runner.downgrade(steps=1)

    async def test_rollback_n_steps(self, db_dir: Path, anyio_backend: str) -> None:
        from arvel.data.migrations import MigrationRunner

        migrations_path = db_dir / "migrations"
        migrations_path.mkdir(exist_ok=True)
        (migrations_path / "versions").mkdir(exist_ok=True)

        runner = MigrationRunner(
            db_url=f"sqlite+aiosqlite:///{db_dir / 'test.db'}",
            migrations_dir=str(migrations_path),
        )
        await runner.downgrade(steps=3)


class TestMigrateFresh:
    """FR-06: migrate:fresh drops all tables and re-runs."""

    async def test_fresh_resets_schema(self, db_dir: Path, anyio_backend: str) -> None:
        from arvel.data.migrations import MigrationRunner

        migrations_path = db_dir / "migrations"
        migrations_path.mkdir(exist_ok=True)
        (migrations_path / "versions").mkdir(exist_ok=True)

        runner = MigrationRunner(
            db_url=f"sqlite+aiosqlite:///{db_dir / 'test.db'}",
            migrations_dir=str(migrations_path),
        )
        await runner.fresh()


class TestMigrateStatus:
    """FR-10: migrate:status shows pending/applied migrations."""

    async def test_status_returns_list(self, db_dir: Path, anyio_backend: str) -> None:
        from arvel.data.migrations import MigrationRunner

        migrations_path = db_dir / "migrations"
        migrations_path.mkdir(exist_ok=True)
        (migrations_path / "versions").mkdir(exist_ok=True)

        runner = MigrationRunner(
            db_url=f"sqlite+aiosqlite:///{db_dir / 'test.db'}",
            migrations_dir=str(migrations_path),
        )
        status = await runner.status()
        assert isinstance(status, list)


class TestMigrateProductionGuard:
    """FR-07, SEC-01: Migration commands require --force in production."""

    async def test_upgrade_blocked_in_production(self, db_dir: Path, anyio_backend: str) -> None:
        from arvel.data.migrations import MigrationRunner

        migrations_path = db_dir / "migrations"
        migrations_path.mkdir(exist_ok=True)
        (migrations_path / "versions").mkdir(exist_ok=True)

        runner = MigrationRunner(
            db_url=f"sqlite+aiosqlite:///{db_dir / 'test.db'}",
            migrations_dir=str(migrations_path),
        )
        with pytest.raises(RuntimeError, match="production"):
            await runner.upgrade(environment="production")

    async def test_upgrade_allowed_with_force_in_production(
        self,
        db_dir: Path,
        anyio_backend: str,
    ) -> None:
        from arvel.data.migrations import MigrationRunner

        migrations_path = db_dir / "migrations"
        migrations_path.mkdir(exist_ok=True)
        (migrations_path / "versions").mkdir(exist_ok=True)

        runner = MigrationRunner(
            db_url=f"sqlite+aiosqlite:///{db_dir / 'test.db'}",
            migrations_dir=str(migrations_path),
        )
        await runner.upgrade(environment="production", force=True)


class TestAsyncEnvPy:
    """FR-09: Alembic env.py runs in async mode."""

    def test_env_template_exists(self) -> None:
        from arvel.data.migrations import MigrationRunner

        template = MigrationRunner.get_env_template()
        assert "run_alembic_env" in template
        assert "from arvel.data.migrations import run_alembic_env" in template


class TestFrameworkMigrationPublishing:
    """Framework migrations are auto-published into the user's migrations dir."""

    def test_register_and_publish_creates_file(self, tmp_path: Path) -> None:
        from arvel.data.migrations import (
            _FRAMEWORK_MIGRATIONS,
            publish_framework_migrations,
            register_framework_migration,
        )

        original_len = len(_FRAMEWORK_MIGRATIONS)
        register_framework_migration(
            "099_create_test_table.py",
            "def upgrade(): pass\ndef downgrade(): pass\n",
        )
        try:
            results = publish_framework_migrations(tmp_path)
            published = [r for r in results if r.action == "published"]
            assert len(published) >= 1
            assert (tmp_path / "099_create_test_table.py").exists()
        finally:
            _FRAMEWORK_MIGRATIONS.pop()
            assert len(_FRAMEWORK_MIGRATIONS) == original_len

    def test_publish_skips_existing_migration_by_stem(self, tmp_path: Path) -> None:
        from arvel.data.migrations import (
            _FRAMEWORK_MIGRATIONS,
            publish_framework_migrations,
            register_framework_migration,
        )

        (tmp_path / "010_create_widgets_table.py").write_text("# custom")
        for _filename, _ in _FRAMEWORK_MIGRATIONS:
            (tmp_path / _filename).write_text("# pre-existing")

        original_len = len(_FRAMEWORK_MIGRATIONS)
        register_framework_migration(
            "099_create_widgets_table.py",
            "def upgrade(): pass\ndef downgrade(): pass\n",
        )
        try:
            results = publish_framework_migrations(tmp_path)
            published = [r for r in results if r.action == "published"]
            assert len(published) == 0
            assert not (tmp_path / "099_create_widgets_table.py").exists()
            content = (tmp_path / "010_create_widgets_table.py").read_text()
            assert content == "# custom"
        finally:
            _FRAMEWORK_MIGRATIONS.pop()
            assert len(_FRAMEWORK_MIGRATIONS) == original_len

    def test_publish_is_idempotent(self, tmp_path: Path) -> None:
        from arvel.data.migrations import (
            _FRAMEWORK_MIGRATIONS,
            publish_framework_migrations,
            register_framework_migration,
        )

        original_len = len(_FRAMEWORK_MIGRATIONS)
        register_framework_migration(
            "099_create_idempotent_table.py",
            "def upgrade(): pass\ndef downgrade(): pass\n",
        )
        try:
            first = publish_framework_migrations(tmp_path)
            second = publish_framework_migrations(tmp_path)
            first_published = [r for r in first if r.action == "published"]
            second_published = [r for r in second if r.action == "published"]
            assert len(first_published) >= 1
            assert len(second_published) == 0
        finally:
            _FRAMEWORK_MIGRATIONS.pop()
            assert len(_FRAMEWORK_MIGRATIONS) == original_len

    def test_media_migration_registered(self) -> None:
        import arvel.media.migration  # noqa: F401
        from arvel.data.migrations import _FRAMEWORK_MIGRATIONS

        filenames = [f for f, _ in _FRAMEWORK_MIGRATIONS]
        assert "003_create_media_table.py" in filenames
