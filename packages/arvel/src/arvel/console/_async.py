"""Async-task deferred execution for CLI commands.

Typer dispatches sync callbacks; commands that need to run async work call
``schedule_async()`` to store their coroutine. The entrypoint reads and
awaits it after Typer returns, on the live event loop.

Only one coroutine can be scheduled per CLI invocation. A second call to
``schedule_async()`` silently overwrites the first — don't do that.
"""

from __future__ import annotations

from collections.abc import Coroutine
from contextvars import ContextVar
from typing import Any

_async_task: ContextVar[Coroutine[Any, Any, Any] | None] = ContextVar("_async_task", default=None)
_async_task_borrowed: ContextVar[bool] = ContextVar("_async_task_borrowed", default=False)


def schedule_async(coro: Coroutine[Any, Any, Any]) -> None:
    """Defer *coro* to run on the CLI's main event loop after Typer dispatch."""
    previous = _async_task.get()
    if previous is not None:
        previous.close()
    _async_task.set(coro)
    _async_task_borrowed.set(False)


def get_pending_task() -> Coroutine[Any, Any, Any] | None:
    """Return the coroutine scheduled via schedule_async, or None."""
    pending = _async_task.get()
    if pending is not None:
        _async_task_borrowed.set(True)
    return pending


def clear_pending_task() -> None:
    """Reset the pending task slot to None."""
    pending = _async_task.get()
    if pending is not None and not _async_task_borrowed.get():
        pending.close()
    _async_task.set(None)
    _async_task_borrowed.set(False)


__all__ = ["clear_pending_task", "get_pending_task", "schedule_async"]
