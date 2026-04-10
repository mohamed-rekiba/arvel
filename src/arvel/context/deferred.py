"""Deferred execution — register tasks to run after the HTTP response is sent.

Uses a ContextVar to collect deferred tasks during request handling.
The DeferredTaskMiddleware drains and executes them after the response body
is fully transmitted.
"""

from __future__ import annotations

import asyncio
import inspect
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import anyio
import anyio.to_thread

from arvel.logging import Log

if TYPE_CHECKING:
    from collections.abc import Callable

    _DeferFn = Callable[[], Any]

logger = Log.named("arvel.context.deferred")


@dataclass(slots=True)
class DeferredTask:
    """A single deferred task registered via ``defer()``."""

    fn: _DeferFn
    name: str | None = None


_EMPTY_TASKS: list[DeferredTask] = []
_deferred_tasks: ContextVar[list[DeferredTask]] = ContextVar("arvel_deferred_tasks")


def defer(fn: _DeferFn, *, name: str | None = None) -> None:
    """Register a callable to run after the HTTP response is sent.

    Both sync and async callables are accepted. Sync callables are
    run in a thread executor. Exceptions are logged, never propagated.
    """
    current = _deferred_tasks.get(_EMPTY_TASKS)
    new_list = [*current, DeferredTask(fn=fn, name=name)]
    _deferred_tasks.set(new_list)


class DeferredCollector:
    """Low-level API for managing the deferred task ContextVar.

    Used by DeferredTaskMiddleware and directly in tests.
    """

    def install(self) -> None:
        """Reset the deferred task list for this context."""
        _deferred_tasks.set([])

    def drain(self) -> list[DeferredTask]:
        """Return and clear all registered deferred tasks."""
        tasks = _deferred_tasks.get(_EMPTY_TASKS)
        _deferred_tasks.set([])
        return list(tasks)

    def reset(self) -> None:
        """Clear the deferred task list."""
        _deferred_tasks.set([])


async def _execute_deferred(tasks: list[DeferredTask], deadline: float) -> None:
    """Execute deferred tasks sequentially within *deadline* seconds."""
    try:
        with anyio.fail_after(deadline):
            for task in tasks:
                task_name = task.name or getattr(task.fn, "__name__", repr(task.fn))
                try:
                    if inspect.iscoroutinefunction(task.fn):
                        await task.fn()
                    elif asyncio.iscoroutine(task.fn):
                        await task.fn
                    else:
                        await anyio.to_thread.run_sync(task.fn)
                except Exception:
                    logger.exception("deferred_task_failed", task=task_name)
    except TimeoutError:
        logger.warning("deferred_tasks_timeout", deadline=deadline)
