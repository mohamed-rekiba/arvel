"""Tests for Story 7: Database Seeding.

Covers: FR-11 through FR-17, SEC-02.
All tests should FAIL until implementation exists.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession

    from arvel.data.observer import ObserverRegistry

from .conftest import AppTransaction, User


class TestSeederBaseClass:
    """FR-12: Seeder base class with async def run(tx)."""

    def test_seeder_importable(self) -> None:
        from arvel.data.seeder import Seeder

        assert Seeder is not None

    def test_seeder_has_run_method(self) -> None:
        from arvel.data.seeder import Seeder

        assert hasattr(Seeder, "run")

    def test_seeder_subclass_instantiable(self) -> None:
        from arvel.data.seeder import Seeder

        class TestSeeder(Seeder):
            async def run(self, tx: Any) -> None:
                pass

        seeder = TestSeeder()
        assert seeder is not None


class TestSeederExecution:
    """FR-12, FR-16: Seeder executes within transaction."""

    async def test_seeder_run_receives_transaction(self, transaction: AppTransaction) -> None:
        from arvel.data.seeder import Seeder

        received_tx = None

        class CapturingSeeder(Seeder):
            async def run(self, tx: Any) -> None:
                nonlocal received_tx
                received_tx = tx

        seeder = CapturingSeeder()
        async with transaction:
            await seeder.run(transaction)

        assert received_tx is transaction

    async def test_seeder_creates_records(
        self, transaction: AppTransaction, db_session: AsyncSession
    ) -> None:
        from arvel.data.seeder import Seeder

        class UserSeeder(Seeder):
            async def run(self, tx: Any) -> None:
                await tx.users.create({"name": "Seeded", "email": "seeded@test.com"})

        seeder = UserSeeder()
        async with transaction:
            await seeder.run(transaction)

        users = await User.query(db_session).where(User.name == "Seeded").all()
        assert len(users) == 1

    async def test_seeder_rollback_on_failure(
        self, db_session: AsyncSession, observer_registry: ObserverRegistry
    ) -> None:
        from arvel.data.seeder import Seeder

        class FailingSeeder(Seeder):
            async def run(self, tx: Any) -> None:
                await tx.users.create({"name": "WillFail", "email": "fail@seed.com"})
                raise RuntimeError("seeder crash")

        seeder = FailingSeeder()
        tx = AppTransaction(session=db_session, observer_registry=observer_registry)

        with pytest.raises(RuntimeError, match="seeder crash"):
            async with tx:
                await seeder.run(tx)

        count = await User.query(db_session).count()
        assert count == 0


class TestSeederDiscovery:
    """FR-13, FR-14: Seeder discovery from directory."""

    def test_discover_seeders_from_directory(self, tmp_path: Path) -> None:
        from arvel.data.seeder import discover_seeders

        seeders_dir = tmp_path / "database" / "seeders"
        seeders_dir.mkdir(parents=True)

        (seeders_dir / "__init__.py").write_text("")
        (seeders_dir / "user_seeder.py").write_text(
            "from arvel.data.seeder import Seeder\n\n"
            "class UserSeeder(Seeder):\n"
            "    async def run(self, tx):\n"
            "        pass\n"
        )

        found = discover_seeders(seeders_dir)
        assert len(found) == 1
        assert found[0].__name__ == "UserSeeder"

    def test_discover_skips_non_seeder_files(self, tmp_path: Path) -> None:
        from arvel.data.seeder import discover_seeders

        seeders_dir = tmp_path / "database" / "seeders"
        seeders_dir.mkdir(parents=True)
        (seeders_dir / "__init__.py").write_text("")
        (seeders_dir / "helpers.py").write_text("x = 42\n")

        found = discover_seeders(seeders_dir)
        assert len(found) == 0

    def test_discover_alphabetical_order(self, tmp_path: Path) -> None:
        from arvel.data.seeder import discover_seeders

        seeders_dir = tmp_path / "database" / "seeders"
        seeders_dir.mkdir(parents=True)
        (seeders_dir / "__init__.py").write_text("")

        for name in ("z_seeder", "a_seeder", "m_seeder"):
            (seeders_dir / f"{name}.py").write_text(
                "from arvel.data.seeder import Seeder\n\n"
                f"class {name.title().replace('_', '')}(Seeder):\n"
                "    async def run(self, tx):\n"
                "        pass\n"
            )

        found = discover_seeders(seeders_dir)
        names = [s.__name__ for s in found]
        assert names == sorted(names)


class TestSeederProductionGuard:
    """FR-15, SEC-02: Seeders refuse in production without --force."""

    def test_seed_runner_importable(self) -> None:
        from arvel.data.seeder import SeedRunner

        assert SeedRunner is not None

    async def test_seed_blocked_in_production(self, tmp_path: Path) -> None:
        from arvel.data.seeder import SeedRunner

        runner = SeedRunner(
            seeders_dir=tmp_path / "database" / "seeders",
            db_url="sqlite+aiosqlite:///test.db",
        )
        with pytest.raises(RuntimeError, match="production"):
            await runner.run(environment="production")

    async def test_seed_allowed_with_force(self, tmp_path: Path) -> None:
        from arvel.data.seeder import SeedRunner

        seeders_dir = tmp_path / "database" / "seeders"
        seeders_dir.mkdir(parents=True)
        (seeders_dir / "__init__.py").write_text("")

        runner = SeedRunner(
            seeders_dir=seeders_dir,
            db_url="sqlite+aiosqlite:///test.db",
        )
        await runner.run(environment="production", force=True)
