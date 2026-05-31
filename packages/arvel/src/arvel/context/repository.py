"""Request-scoped context repository, backed by a contextvar.

Laravel's ``Context`` ported to async Python. The active repository is held in a
``ContextVar`` so each request (or each ``asyncio`` task tree) gets its own store
without passing it around. ``ContextMiddleware`` swaps in a fresh repository per
request and resets it on teardown.

Two stores live side by side:

- **visible** data — round-trips to queued jobs via ``dehydrate``/``hydrate`` and
  shows up in ``all()``.
- **hidden** data — never serialized, never in ``all()``. Use it for things that
  must stay in-process (tokens, internal ids).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from typing import Any, cast

# A deferred callback runs after the response is sent. It may be sync or async.
DeferredCallback = Callable[[], Awaitable[None] | None]


class ContextRepository:
    """Per-request key/value store with a separate hidden namespace."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._hidden: dict[str, Any] = {}
        self._deferred: list[DeferredCallback] = []

    def add(self, key: str, value: Any) -> ContextRepository:
        self._data[key] = value
        return self

    def add_hidden(self, key: str, value: Any) -> ContextRepository:
        self._hidden[key] = value
        return self

    def push(self, key: str, *values: Any) -> ContextRepository:
        # `current` stays typed `object` (the check helper doesn't narrow it), so the
        # cast is a real object→list[Any] cast — non-redundant for mypy, and it
        # resolves the element type for pyright.
        current: object = self._data.get(key, [])
        _require_list(current, key)
        bucket = cast("list[Any]", current)
        bucket.extend(values)
        self._data[key] = bucket
        return self

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def get_hidden(self, key: str, default: Any = None) -> Any:
        return self._hidden.get(key, default)

    def has(self, key: str) -> bool:
        return key in self._data

    def has_hidden(self, key: str) -> bool:
        return key in self._hidden

    def forget(self, key: str) -> ContextRepository:
        self._data.pop(key, None)
        return self

    def forget_hidden(self, key: str) -> ContextRepository:
        self._hidden.pop(key, None)
        return self

    def all(self) -> dict[str, Any]:
        """Visible keys only — hidden keys never appear here."""
        return dict(self._data)

    def all_hidden(self) -> dict[str, Any]:
        return dict(self._hidden)

    def keys(self) -> list[str]:
        return list(self._data)

    def is_empty(self) -> bool:
        return not self._data and not self._hidden

    def defer(self, callback: DeferredCallback) -> ContextRepository:
        self._deferred.append(callback)
        return self

    def deferred(self) -> list[DeferredCallback]:
        return list(self._deferred)

    def flush(self) -> ContextRepository:
        self._data.clear()
        self._hidden.clear()
        self._deferred.clear()
        return self

    def dehydrate(self) -> dict[str, Any]:
        """Visible keys as a plain dict, ready to ride along with a queued job.

        Hidden keys are excluded by design — they must not leave the process.
        """
        return dict(self._data)

    def hydrate(self, data: dict[str, Any]) -> ContextRepository:
        """Restore visible keys from a ``dehydrate()`` payload (queue worker side)."""
        self._data.update(data)
        return self


def _require_list(value: object, key: str) -> None:
    """Guard for ``push`` — raises if the existing value isn't a list. Doesn't narrow."""
    if not isinstance(value, list):
        msg = f"Context key {key!r} is not a list; cannot push onto it."
        raise TypeError(msg)


_active: ContextVar[ContextRepository | None] = ContextVar("arvel_context", default=None)


def current_repository() -> ContextRepository:
    """The active repository, creating a lazy one outside a request/middleware."""
    repo = _active.get()
    if repo is None:
        repo = ContextRepository()
        _active.set(repo)
    return repo


def bind_repository(repo: ContextRepository) -> Token[ContextRepository | None]:
    return _active.set(repo)


def reset_repository(token: Token[ContextRepository | None]) -> None:
    _active.reset(token)


__all__ = [
    "ContextRepository",
    "DeferredCallback",
    "bind_repository",
    "current_repository",
    "reset_repository",
]
