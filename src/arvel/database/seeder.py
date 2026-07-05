"""arvel.database.seeder — the Seeder base.

Subclass and implement ``run()`` to insert seed data; ``call(*Seeders)`` chains child seeders
from a ``DatabaseSeeder``. The ``db:seed`` command runs the app's bound root seeder. Grounded
in knowledge/port/08-advanced-database.md.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from typing import Any

from arvel.contracts import CommandOutput
from arvel.database.model_events import EVENTS_SUPPRESSED


class _NullOutput:
    """The default seeder output: silent no-ops, so a seeder run outside the ``db:seed`` command
    (tests, a script) prints nothing and ``with_progress_bar`` simply iterates. The ``db:seed``
    runner swaps in the real ``arvel.console`` output — the ``database`` layer never imports it,
    depending on the :class:`~arvel.contracts.CommandOutput` contract instead."""

    def info(self, message: str) -> None: ...
    def line(self, message: str = "") -> None: ...
    def comment(self, message: str) -> None: ...
    def warn(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...
    def new_line(self, n: int = 1) -> None: ...
    def table(self, headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> None: ...

    def with_progress_bar(self, iterable: Iterable[Any], *, label: str = "") -> Iterator[Any]:
        yield from iterable


_NULL_OUTPUT: CommandOutput = _NullOutput()

# Which seeder classes `call_once` has already run in the current seeding run, so a seeder
# reachable from multiple `call()` chains runs once. Reset per run (see
# `reset_called_once`, invoked by the seed entrypoint) — NOT process-lifetime, or a long-lived
# worker / repeated `db:seed` would silently skip every once-seeder after the first run.
_called_once: set[type[Seeder]] = set()


def reset_called_once() -> None:
    """Clear the `call_once` dedup set — the seed entrypoint calls this so each run starts fresh."""
    _called_once.clear()


class Seeder:
    """Base seeder: override ``run()``; use ``call()`` to invoke child seeders.

    ``output`` is the console handle the ``db:seed`` runner injects (a :class:`_NullOutput` until
    then). Use it for feedback on a long seed: wrap a slow loop in ``self.with_progress_bar(...)``
    and print section headers with ``self.line(...)``. Child seeders started via ``call``/
    ``call_once`` inherit the same output, so progress is consistent across the whole tree."""

    output: CommandOutput = _NULL_OUTPUT

    async def run(self) -> None:
        raise NotImplementedError(f"{type(self).__name__} must implement run()")

    async def call(self, *seeders: type[Seeder]) -> None:
        for seeder in seeders:
            child = seeder()
            child.output = self.output
            await child.run()

    async def call_once(self, *seeders: type[Seeder]) -> None:
        """Like :meth:`call`, but skips a seeder class already run (by ``call_once``) this process —
        so a shared seeder (e.g. a roles seeder several other seeders depend on) runs exactly once
        however many times it's reached."""
        for seeder in seeders:
            if seeder in _called_once:
                continue
            _called_once.add(seeder)
            child = seeder()
            child.output = self.output
            await child.run()

    # -- output (delegates to the injected console handle) --------------------------------------
    def line(self, message: str = "") -> None:
        self.output.line(message)

    def info(self, message: str) -> None:
        self.output.info(message)

    def with_progress_bar(self, iterable: Iterable[Any], *, label: str = "") -> Iterator[Any]:
        """Iterate ``iterable`` while rendering a progress bar (a no-op iteration until the
        ``db:seed`` runner injects a real output). The loop body may ``await`` — the bar advances as
        each item is consumed::

            for user in self.with_progress_bar(rows, label='users'):
                await User.create(**user)
        """
        return self.output.with_progress_bar(iterable, label=label)


class WithoutModelEvents:
    """Context manager: suppress model lifecycle events (``creating``/``saved``/…) for its duration
    — wrap a seeder's bulk inserts in it so observers don't
       fan out per row::

           async def run(self) -> None:
               with WithoutModelEvents():
                   await UserFactory().count(1000).create()
    """

    def __enter__(self) -> None:
        self._token = EVENTS_SUPPRESSED.set(True)

    def __exit__(self, *exc_info: object) -> None:
        EVENTS_SUPPRESSED.reset(self._token)
