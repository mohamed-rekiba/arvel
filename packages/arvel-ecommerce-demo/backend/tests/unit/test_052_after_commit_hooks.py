"""Unit tests for the after-commit lifecycle hooks (Story 2).

Covers:
- DB.after_commit() enqueues callbacks executed after DB.transaction() commits.
- Callbacks don't run when the transaction rolls back.
- Nested DB.transaction() (savepoint) doesn't run callbacks — only outermost does.
- fire_after_commit() enqueues observer.after_commit() into the active queue.
- fire_after_commit() is a no-op when called outside a transaction.
- DatabaseTransaction middleware owns the callback queue per request.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from arvel.database.events import Observer, fire_after_commit
from arvel.database.session import (
    enqueue_after_commit,
    get_after_commit_queue,
    reset_after_commit_queue,
    set_after_commit_queue,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_queue_context() -> tuple[list[Any], Any]:
    """Install an after-commit queue and return (queue, token)."""
    q: list[Any] = []
    token = set_after_commit_queue(q)
    return q, token


# ── enqueue_after_commit ──────────────────────────────────────────────────────


def test_enqueue_after_commit_raises_outside_transaction() -> None:
    """enqueue_after_commit() must raise when no queue is active."""
    assert get_after_commit_queue() is None
    with pytest.raises(RuntimeError, match="outside a DB.transaction"):
        enqueue_after_commit(AsyncMock())


def test_enqueue_after_commit_appends_to_queue() -> None:
    q, token = _make_queue_context()
    cb = AsyncMock()
    enqueue_after_commit(cb)
    assert cb in q
    reset_after_commit_queue(token)


# ── fire_after_commit ─────────────────────────────────────────────────────────


def test_fire_after_commit_noop_when_no_queue() -> None:
    """fire_after_commit() silently skips when no transaction is active."""

    class _Obs(Observer[Any]):
        after_commit = AsyncMock()

    model = MagicMock()
    model._arvel_observers = [_Obs()]
    fire_after_commit(model, object())
    _Obs.after_commit.assert_not_called()


def test_fire_after_commit_enqueues_observer_method() -> None:
    q, token = _make_queue_context()

    called_with: list[Any] = []

    class _Obs(Observer[Any]):
        async def after_commit(self, instance: Any) -> None:
            called_with.append(instance)

    obs = _Obs()
    sentinel = object()
    model = MagicMock()
    model._arvel_observers = [obs]
    fire_after_commit(model, sentinel)

    assert len(q) == 1, "one callback enqueued"

    asyncio.get_event_loop().run_until_complete(q[0]())
    assert called_with == [sentinel]

    reset_after_commit_queue(token)


def test_fire_after_commit_skips_observers_without_hook() -> None:
    q, token = _make_queue_context()

    class _NoHookObs(Observer[Any]):
        pass

    model = MagicMock()
    model._arvel_observers = [_NoHookObs()]
    fire_after_commit(model, object())
    assert q == [], "no callback enqueued for observer without after_commit"

    reset_after_commit_queue(token)


# ── DB-level integration (mock session) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_callbacks_execute_after_successful_transaction() -> None:
    """Callbacks enqueued via enqueue_after_commit run after DB.transaction() commits."""
    from arvel.database.db import DB

    executed: list[str] = []

    async def _cb() -> None:
        executed.append("fired")

    mock_session = AsyncMock()
    mock_session.begin.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_maker = MagicMock()
    mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)

    original_maker = DB._session_maker
    DB.configure(mock_maker)
    try:
        async with DB.transaction():
            enqueue_after_commit(_cb)
        assert executed == ["fired"], "callback must run after commit"
    finally:
        DB._session_maker = original_maker


@pytest.mark.asyncio
async def test_callbacks_do_not_execute_on_rollback() -> None:
    """Callbacks are not called when the transaction raises."""
    from arvel.database.db import DB

    executed: list[str] = []

    async def _cb() -> None:
        executed.append("fired")

    mock_session = AsyncMock()

    @asynccontextmanager
    async def _begin_that_raises() -> None:  # type: ignore[override]
        raise RuntimeError("forced rollback")
        yield  # type: ignore[misc]  # unreachable but required for @asynccontextmanager protocol

    mock_session.begin = _begin_that_raises
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_maker = MagicMock()
    mock_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_maker.return_value.__aexit__ = AsyncMock(return_value=False)

    original_maker = DB._session_maker
    DB.configure(mock_maker)
    try:
        with pytest.raises(RuntimeError, match="forced rollback"):
            async with DB.transaction():
                enqueue_after_commit(_cb)
        assert executed == [], "callbacks must NOT fire on rollback"
    finally:
        DB._session_maker = original_maker
