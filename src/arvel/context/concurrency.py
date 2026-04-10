"""Structured concurrency utility — parallel task execution with anyio."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

import anyio

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

_T = TypeVar("_T")


class Concurrency:
    """Run independent async tasks in parallel with structured cancellation.

    Uses ``anyio.create_task_group()`` for backend-agnostic concurrency.
    """

    __slots__ = ()

    @staticmethod
    async def run(
        tasks: Sequence[Callable[[], Awaitable[_T]]],
        *,
        deadline: float | None = None,
    ) -> list[_T]:
        """Execute *tasks* in parallel, returning results in input order.

        Fail-fast: if any task raises, remaining tasks are cancelled and
        the exception propagates. An optional *deadline* (seconds) cancels
        all tasks if exceeded.

        Raises:
            TimeoutError: If *deadline* is exceeded.
        """
        if not tasks:
            return []

        results: dict[int, _T] = {}

        async def _run_indexed(index: int, fn: Callable[[], Awaitable[_T]]) -> None:
            results[index] = await fn()

        async def _inner() -> list[_T]:
            async with anyio.create_task_group() as tg:
                for i, fn in enumerate(tasks):
                    tg.start_soon(_run_indexed, i, fn)
            return [results[i] for i in range(len(tasks))]

        if deadline is not None:
            with anyio.fail_after(deadline):
                return await _inner()
        return await _inner()

    @staticmethod
    async def gather(
        tasks: Sequence[Callable[[], Awaitable[_T]]],
        *,
        return_exceptions: bool = False,
    ) -> list[_T | BaseException]:
        """Execute *tasks* in parallel, collecting all results.

        If *return_exceptions* is ``False`` (default), the first exception
        is re-raised. If ``True``, exception objects appear in the result
        list at the position of the failed task.
        """
        if not tasks:
            return []

        if not return_exceptions:
            return await Concurrency.run(tasks)

        results: dict[int, _T | BaseException] = {}

        async def _run_safe(index: int, fn: Callable[[], Awaitable[_T]]) -> None:
            try:
                results[index] = await fn()
            except Exception as exc:
                results[index] = exc

        async with anyio.create_task_group() as tg:
            for i, fn in enumerate(tasks):
                tg.start_soon(_run_safe, i, fn)

        return [results[i] for i in range(len(tasks))]
