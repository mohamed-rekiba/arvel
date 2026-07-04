"""arvel.database.seeder — the Seeder base (Laravel ``Seeder``).

Subclass and implement ``run()`` to insert seed data; ``call(*Seeders)`` chains child seeders
from a ``DatabaseSeeder``. The ``db:seed`` command runs the app's bound root seeder. Grounded
in knowledge/port/08-advanced-database.md.
"""

from __future__ import annotations

from arvel.database.model_events import EVENTS_SUPPRESSED

# Process-wide: which seeder classes `call_once` has already run, so a seeder reachable from
# multiple `call()` chains within the same process only actually runs once (Laravel `callOnce`).
_called_once: set[type[Seeder]] = set()


class Seeder:
    """Base seeder: override ``run()``; use ``call()`` to invoke child seeders."""

    async def run(self) -> None:
        raise NotImplementedError(f"{type(self).__name__} must implement run()")

    async def call(self, *seeders: type[Seeder]) -> None:
        for seeder in seeders:
            await seeder().run()

    async def call_once(self, *seeders: type[Seeder]) -> None:
        """Like :meth:`call`, but skips a seeder class already run (by ``call_once``) this process —
        so a shared seeder (e.g. a roles seeder several other seeders depend on) runs exactly once
        however many times it's reached."""
        for seeder in seeders:
            if seeder in _called_once:
                continue
            _called_once.add(seeder)
            await seeder().run()


class WithoutModelEvents:
    """Context manager: suppress model lifecycle events (``creating``/``saved``/…) for its duration
    (Laravel's ``WithoutModelEvents`` trait) — wrap a seeder's bulk inserts in it so observers don't
    fan out per row::

        async def run(self) -> None:
            with WithoutModelEvents():
                await UserFactory().count(1000).create()
    """

    def __enter__(self) -> None:
        self._token = EVENTS_SUPPRESSED.set(True)

    def __exit__(self, *exc_info: object) -> None:
        EVENTS_SUPPRESSED.reset(self._token)
