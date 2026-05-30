"""Active-session context for ActiveRecord helpers.

``Model.create(...)``, ``user.save()``, ``QueryBuilder.first()`` etc. need an
``AsyncSession`` but should not require passing it in every call. We expose a
``ContextVar`` that ``DatabaseServiceProvider`` populates at request scope and
that tests populate via ``set_active_session(...)`` in fixtures.

A second ContextVar, ``_AFTER_COMMIT_CALLBACKS``, holds the callback queue for
the current transaction.  ``DatabaseTransaction`` middleware and
``DB.transaction()`` own the queue lifecycle; ``DB.after_commit()`` appends to
it.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar, Token
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

_ACTIVE_SESSION: ContextVar[AsyncSession | None] = ContextVar("arvel_active_session", default=None)

# Holds the list of async callbacks to fire after the current transaction commits.
# None means no transaction is managing the queue (DB.after_commit() will raise).
_AFTER_COMMIT_CALLBACKS: ContextVar[list[Callable[[], Awaitable[Any]]] | None] = ContextVar(
    "arvel_after_commit_callbacks", default=None
)


class NoActiveSessionError(RuntimeError):
    """Raised when ActiveRecord helpers run without a session in scope."""

    def __init__(self) -> None:
        super().__init__(
            "No active database session. Make sure DatabaseServiceProvider is "
            "registered, or call arvel.database.session.set_active_session(...) "
            "inside the test scope."
        )


def get_optional_session() -> AsyncSession | None:
    """Return the active session or None — does not raise."""
    return _ACTIVE_SESSION.get()


def get_active_session() -> AsyncSession:
    """Return the session bound to the current async context.

    Raises :class:`NoActiveSessionError` if none is bound.
    """
    session = _ACTIVE_SESSION.get()
    if session is None:
        raise NoActiveSessionError
    return session


def set_active_session(session: AsyncSession | None) -> Token[AsyncSession | None]:
    """Set the active session and return a token usable with ``reset_active_session``."""
    return _ACTIVE_SESSION.set(session)


def reset_active_session(token: Token[AsyncSession | None]) -> None:
    _ACTIVE_SESSION.reset(token)


@asynccontextmanager
async def use_session(session: AsyncSession) -> AsyncGenerator[AsyncSession]:
    """Context manager binding ``session`` as the active session for its scope."""
    token = set_active_session(session)
    try:
        yield session
    finally:
        reset_active_session(token)


# ── after-commit queue ─────────────────────────────────────────────────────


def get_after_commit_queue() -> list[Callable[[], Awaitable[Any]]] | None:
    """Return the active after-commit callback queue, or None if outside a transaction."""
    return _AFTER_COMMIT_CALLBACKS.get()


def set_after_commit_queue(
    queue: list[Callable[[], Awaitable[Any]]],
) -> Token[list[Callable[[], Awaitable[Any]]] | None]:
    """Install ``queue`` as the active after-commit callback list."""
    return _AFTER_COMMIT_CALLBACKS.set(queue)


def reset_after_commit_queue(
    token: Token[list[Callable[[], Awaitable[Any]]] | None],
) -> None:
    _AFTER_COMMIT_CALLBACKS.reset(token)


def enqueue_after_commit(fn: Callable[[], Awaitable[Any]]) -> None:
    """Append ``fn`` to the active after-commit queue.

    Raises ``RuntimeError`` if called outside a transaction context (no queue
    is currently set by ``DB.transaction()`` or ``DatabaseTransaction``
    middleware).
    """
    queue = _AFTER_COMMIT_CALLBACKS.get()
    if queue is None:
        raise RuntimeError(
            "DB.after_commit() called outside a DB.transaction() block or HTTP request. "
            "Wrap the call in DB.transaction() or ensure DatabaseTransaction middleware "
            "is installed."
        )
    queue.append(fn)


__all__ = [
    "NoActiveSessionError",
    "enqueue_after_commit",
    "get_active_session",
    "get_after_commit_queue",
    "get_optional_session",
    "reset_active_session",
    "reset_after_commit_queue",
    "set_active_session",
    "set_after_commit_queue",
    "use_session",
]
