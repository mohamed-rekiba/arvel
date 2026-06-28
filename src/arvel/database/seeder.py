"""arvel.database.seeder — the Seeder base (Laravel ``Seeder``).

Subclass and implement ``run()`` to insert seed data; ``call(*Seeders)`` chains child seeders
from a ``DatabaseSeeder``. The ``db:seed`` command runs the app's bound root seeder. Grounded
in knowledge/port/08-advanced-database.md.
"""

from __future__ import annotations


class Seeder:
    """Base seeder: override ``run()``; use ``call()`` to invoke child seeders."""

    async def run(self) -> None:
        raise NotImplementedError(f"{type(self).__name__} must implement run()")

    async def call(self, *seeders: type[Seeder]) -> None:
        for seeder in seeders:
            await seeder().run()
