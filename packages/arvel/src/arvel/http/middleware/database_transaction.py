"""Sanctioned HTTP↔database bridge.

This is the ONLY HTTP module allowed to import ``arvel.database``. It opens an
``AsyncSession`` per request, binds it as the active session for ActiveRecord
helpers, runs the handler inside a transaction (``session.begin``), commits
on a successful 2xx/3xx response, and rolls back on exception or 4xx/5xx.

After a successful commit, any callbacks registered via ``DB.after_commit``
during request handling are awaited before the response is returned.

The exemption is enforced by ``tests/architecture/test_layering.py``
(``ALLOWED_HTTP_TO_DATABASE_IMPORTS``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arvel.database.session import (
    reset_active_session,
    reset_after_commit_queue,
    set_active_session,
    set_after_commit_queue,
)
from arvel.http._middleware_core import CallNext

_HTTP_ERROR_THRESHOLD = 400


class DatabaseTransaction:
    """Wrap each request in a database transaction.

    The session-maker is resolved from the request's container (set up by
    Arvel's ASGI integration). Tests may supply a session-maker directly via
    the constructor for unit testing.
    """

    def __init__(self, session_maker: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._explicit_maker = session_maker

    async def handle(self, request: Any, call_next: CallNext) -> Any:
        maker = self._resolve_maker(request)
        callbacks: list[Callable[[], Awaitable[Any]]] = []
        q_token = set_after_commit_queue(callbacks)
        try:
            return await self._run(request, call_next, maker, callbacks)
        finally:
            reset_after_commit_queue(q_token)

    async def _run(
        self,
        request: Any,
        call_next: CallNext,
        maker: async_sessionmaker[AsyncSession],
        callbacks: list[Callable[[], Awaitable[Any]]],
    ) -> Any:
        async with maker() as session:
            token = set_active_session(session)
            response: Any = None
            try:
                async with session.begin():
                    response = await call_next(request)
                    _raise_if_error(response)
            except _ResponseRollback as r:
                return r.response
            else:
                for cb in callbacks:
                    await cb()
                return response
            finally:
                reset_active_session(token)

    def _resolve_maker(self, request: Any) -> async_sessionmaker[AsyncSession]:
        if self._explicit_maker is not None:
            return self._explicit_maker
        app = getattr(request, "app", None)
        container = getattr(getattr(app, "state", None), "arvel_container", None)
        if container is None:
            raise RuntimeError(
                "DatabaseTransaction middleware needs request.app.state.arvel_container."
            )
        maker: async_sessionmaker[AsyncSession] = container.make(async_sessionmaker[AsyncSession])
        return maker


class _ResponseRollback(BaseException):
    """Internal sentinel: propagate the response while rolling back the txn."""

    def __init__(self, response: Any) -> None:
        super().__init__("rollback")
        self.response = response


def _raise_if_error(response: Any) -> None:
    """Trigger rollback by raising _ResponseRollback when the handler returned >=400.

    Lifted out so ruff's TRY301 (raise-within-try) is satisfied.
    """
    if _is_error_response(response):
        raise _ResponseRollback(response)


def _is_error_response(response: Any) -> bool:
    status = getattr(response, "status_code", 200)
    try:
        return int(status) >= _HTTP_ERROR_THRESHOLD
    except TypeError, ValueError:
        return False


__all__ = ["DatabaseTransaction"]
