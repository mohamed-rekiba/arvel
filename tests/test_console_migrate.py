"""Console (doc 13) — migrate runs the app's bound migrations via the bound migrator."""

from __future__ import annotations

from typing import Any

from typer.testing import CliRunner

from arvel.console import build_cli
from arvel.database import ConnectionResolver, Migrator, Seeder
from arvel.database.migrations import Migration, Schema

runner = CliRunner()


class CreateWidgets(Migration):
    def up(self, schema: Schema) -> None:
        schema.create("widgets", lambda t: [t.id(), t.string("name")])

    def down(self, schema: Schema) -> None:
        schema.drop("widgets")


def test_migrate_applies_bound_migrations() -> None:
    from arvel.kernel import Application, set_application

    db = ConnectionResolver()
    app = Application()
    app.instance("migrator", Migrator(db))
    app.instance("migrations", [CreateWidgets()])
    set_application(app)
    try:
        result = runner.invoke(build_cli(), ["migrate"])
        assert result.exit_code == 0, result.output
        assert "migrated 1 migration" in result.output
    finally:
        set_application(None)


def test_migrate_without_migrator_errors() -> None:
    from arvel.kernel import Application, set_application

    set_application(Application())  # active app, but no 'migrator' bound → binding-missing branch
    try:
        result = runner.invoke(build_cli(), ["migrate"])
        assert result.exit_code == 1
        assert "no migrator bound" in result.output
    finally:
        set_application(None)


class CreateGadgets(Migration):
    def up(self, schema: Schema) -> None:
        schema.create("gadgets", lambda t: [t.id()])

    def down(self, schema: Schema) -> None:
        schema.drop("gadgets")


def test_migrate_rollback_reverts() -> None:
    from arvel.kernel import Application, set_application

    db = ConnectionResolver()
    migrator = Migrator(db)
    app = Application()
    app.instance("migrator", migrator)
    app.instance("migrations", [CreateGadgets()])
    set_application(app)
    try:
        assert runner.invoke(build_cli(), ["migrate"]).exit_code == 0
        result = runner.invoke(build_cli(), ["migrate:rollback", "--force"])
        assert result.exit_code == 0, result.output
        assert "rolled back 1 migration" in result.output
    finally:
        set_application(None)


def _app_with(migration: Migration) -> tuple[Any, Any]:
    from arvel.kernel import Application, set_application

    app = Application()
    app.instance("migrator", Migrator(ConnectionResolver()))
    app.instance("migrations", [migration])
    set_application(app)
    return app, set_application


def test_migrate_fresh_drops_then_remigrates() -> None:
    _, reset = _app_with(CreateWidgets())
    try:
        assert runner.invoke(build_cli(), ["migrate"]).exit_code == 0
        result = runner.invoke(build_cli(), ["migrate:fresh", "--force"])
        assert result.exit_code == 0, result.output
        assert "dropped" in result.output and "migrated 1 migration" in result.output
    finally:
        reset(None)


def test_migrate_refresh_rolls_back_then_remigrates() -> None:
    _, reset = _app_with(CreateWidgets())
    try:
        assert runner.invoke(build_cli(), ["migrate"]).exit_code == 0
        result = runner.invoke(build_cli(), ["migrate:refresh", "--force"])
        assert result.exit_code == 0, result.output
        assert "refreshed 1 migration" in result.output
    finally:
        reset(None)


def test_migrate_refresh_seed_reseeds() -> None:
    from arvel.kernel import Application, set_application

    ran: list[str] = []

    class RootSeeder(Seeder):
        async def run(self) -> None:
            ran.append("seeded")

    app = Application()
    app.instance("migrator", Migrator(ConnectionResolver()))
    app.instance("migrations", [CreateWidgets()])
    app.instance("seeder", RootSeeder())
    set_application(app)
    try:
        assert runner.invoke(build_cli(), ["migrate"]).exit_code == 0
        result = runner.invoke(build_cli(), ["migrate:refresh", "--seed", "--force"])
        assert result.exit_code == 0, result.output
        assert "refreshed 1 migration" in result.output
        assert "seeding complete" in result.output
        assert ran == ["seeded"]
    finally:
        set_application(None)


def test_migrate_refresh_without_seed_flag_does_not_seed() -> None:
    from arvel.kernel import Application, set_application

    ran: list[str] = []

    class RootSeeder(Seeder):
        async def run(self) -> None:
            ran.append("seeded")

    app = Application()
    app.instance("migrator", Migrator(ConnectionResolver()))
    app.instance("migrations", [CreateWidgets()])
    app.instance("seeder", RootSeeder())
    set_application(app)
    try:
        assert runner.invoke(build_cli(), ["migrate"]).exit_code == 0
        result = runner.invoke(build_cli(), ["migrate:refresh", "--force"])
        assert result.exit_code == 0, result.output
        assert ran == []
    finally:
        set_application(None)


def test_db_wipe_without_force_refuses_before_dropping() -> None:
    """Wiring proof: the guard runs *before* the drop. A non-interactive db:wipe (CliRunner stdin
    is not a TTY) refuses with exit 1 and never reaches drop_all — the fix is wired, not just
    present."""
    from arvel.kernel import Application, set_application

    calls: list[str] = []

    class SpyMigrator:
        async def drop_all(self) -> int:
            calls.append("drop_all")
            return 0

    app = Application()
    app.instance("migrator", SpyMigrator())
    app.instance("migrations", [])
    set_application(app)
    try:
        result = runner.invoke(build_cli(), ["db:wipe"])  # no --force, non-TTY
        assert result.exit_code == 1, result.output
        assert calls == []  # guard refused before any drop
    finally:
        set_application(None)


def test_db_wipe_drops_all_tables() -> None:
    _, reset = _app_with(CreateWidgets())
    try:
        assert runner.invoke(build_cli(), ["migrate"]).exit_code == 0
        result = runner.invoke(build_cli(), ["db:wipe", "--force"])
        assert result.exit_code == 0, result.output
        assert "dropped" in result.output
    finally:
        reset(None)


def test_migrate_is_idempotent() -> None:
    """Running migrate twice doesn't re-run applied migrations (no 'already exists') — the second run
    is a no-op. This is the bug that crashed `make setup` on an already-migrated database."""
    _, reset = _app_with(CreateWidgets())
    try:
        first = runner.invoke(build_cli(), ["migrate"])
        assert first.exit_code == 0 and "migrated 1 migration" in first.output
        second = runner.invoke(build_cli(), ["migrate"])
        assert second.exit_code == 0, second.output
        assert "Nothing to migrate" in second.output
    finally:
        reset(None)
