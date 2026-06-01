"""DatabaseSeeder — populates rows for development and test environments."""

from __future__ import annotations

from arvel.database import Seeder


class DatabaseSeeder(Seeder):
    """Populate the database with reference / fixture data."""

    async def run(self) -> None:
        pass
