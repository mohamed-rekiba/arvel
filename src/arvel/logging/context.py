"""Public context-store helpers for structured logging."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from structlog.contextvars import (
    bind_contextvars,
    clear_contextvars,
    reset_contextvars,
    unbind_contextvars,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from contextvars import Token
    from typing import Any


def bind_log_context(**context: object) -> Mapping[str, Token[Any]]:
    """Bind context values for subsequent log events in this execution context."""
    return bind_contextvars(**context)


def unbind_log_context(*keys: str) -> None:
    """Remove specific context keys from the current execution context."""
    unbind_contextvars(*keys)


def clear_log_context() -> None:
    """Clear all bound log context for the current execution context."""
    clear_contextvars()


@contextmanager
def scoped_log_context(**context: object) -> Iterator[None]:
    """Temporarily bind log context and restore previous values on exit."""
    tokens = bind_log_context(**context)
    try:
        yield
    finally:
        reset_contextvars(**tokens)
