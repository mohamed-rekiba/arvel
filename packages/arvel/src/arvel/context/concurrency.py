"""``Concurrency`` — run several async tasks at once, results in order."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar

_T = TypeVar("_T")

# A task is a no-arg callable returning an awaitable (e.g. an `async def`).
Task = Callable[[], Awaitable[_T]]


class Concurrency:
    """Fan-out helper. Mirrors Laravel's ``Concurrency::run``."""

    @staticmethod
    async def run(tasks: Sequence[Task[_T]]) -> list[_T]:
        """Run ``tasks`` concurrently, returning results in input order.

        If any task raises, the exception propagates — it is never swallowed.
        """
        return list(await asyncio.gather(*(task() for task in tasks)))

    @staticmethod
    def defer(tasks: Sequence[Task[_T]]) -> asyncio.Task[list[_T]]:
        """Fire-and-forget: schedule the tasks and return the wrapping ``asyncio.Task``."""
        return asyncio.ensure_future(Concurrency.run(tasks))


__all__ = ["Concurrency", "Task"]
