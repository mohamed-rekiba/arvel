"""SQL query capture helper — QueryLog.capture() and QueryLog.assert_max_queries()."""

from __future__ import annotations

from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.engine import Connection, Engine

# Signature of SQLAlchemy cursor event handlers.
_CursorExecuteHandler = Callable[[Any, Any, Any, Any, Any, Any], None]


def _empty_str_list() -> list[str]:
    return []


@dataclass
class _QueryLog:
    queries: list[str] = field(default_factory=_empty_str_list)


class QueryLog:
    """Lightweight test helper for capturing SQL queries in a with-block."""

    @staticmethod
    @contextmanager
    def capture() -> Generator[_QueryLog]:
        """Context manager that captures SQL text of every executed statement.

        Usage::

            with QueryLog.capture() as log:
                await SomeModel.all()
            assert len(log.queries) <= 2
        """
        from sqlalchemy import event as sqla_event

        log = _QueryLog()
        handlers_added: list[tuple[Engine, _CursorExecuteHandler]] = []

        def _on_execute(
            conn: Any,
            cursor: Any,
            statement: Any,
            parameters: Any,
            context: Any,
            executemany: Any,
        ) -> None:
            log.queries.append(str(statement))

        from arvel.database.session import get_optional_session

        session = get_optional_session()
        if session is not None:
            bind: Engine | Connection = session.get_bind()
            sync_engine: Engine = bind.engine if isinstance(bind, Connection) else bind
            sqla_event.listen(sync_engine, "after_cursor_execute", _on_execute)
            handlers_added.append((sync_engine, _on_execute))

        try:
            yield log
        finally:
            for eng, handler in handlers_added:
                if sqla_event.contains(eng, "after_cursor_execute", handler):
                    sqla_event.remove(eng, "after_cursor_execute", handler)

    @staticmethod
    @contextmanager
    def assert_max_queries(n: int) -> Generator[_QueryLog]:
        """Context manager that fails if more than ``n`` queries are issued.

        Usage::

            async with QueryLog.assert_max_queries(2):
                owners = await Owner.with_("items").all()
                _ = owners[0].items  # no extra query — already loaded
        """
        with QueryLog.capture() as log:
            yield log
        if len(log.queries) > n:
            detail = "\n".join(f"  [{i + 1}] {q[:120]}" for i, q in enumerate(log.queries))
            raise AssertionError(f"Expected ≤ {n} queries but got {len(log.queries)}:\n{detail}")


__all__ = ["QueryLog"]
