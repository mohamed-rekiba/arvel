"""arvel.support.context — an ambient, contextvars-backed key/value store (`Context`
parity), safe across concurrent `asyncio` tasks: each task gets its own copy-on-write snapshot,
so a request/job never sees another's context. Every mutator replaces the backing dict wholesale
rather than mutating it in place — that's what makes the per-task isolation hold.

`Context` is a static namespace (no instances — like `Str`/`Number`). Hidden values
(`add_hidden`/…) never appear in `all()`. `dehydrate()`/`hydrate()` round-trip the whole state
(visible + hidden) into a plain, msgspec-serializable payload — the caller's contract is that
every stored value serializes; QUEUE-RELIABILITY wires this into job carry-over.
"""

from __future__ import annotations

import contextvars
import copy
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Any, TypedDict


class ContextPayload(TypedDict):
    """The wire shape produced by `Context.dehydrate()` / consumed by `Context.hydrate()`."""

    visible: dict[str, Any]
    hidden: dict[str, Any]


#: `default=None` (not `{}`) — a mutable default would be one shared dict across every context
#: that never called `.set()`; `_visible_get`/`_hidden_get` paper over the `None` case.
_visible: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "arvel_context_visible", default=None
)
_hidden: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "arvel_context_hidden", default=None
)
_dehydrating: list[Callable[[ContextPayload], None]] = []
_hydrated: list[Callable[[ContextPayload], None]] = []


def _visible_get() -> dict[str, Any]:
    return _visible.get() or {}


def _hidden_get() -> dict[str, Any]:
    return _hidden.get() or {}


class Context:
    """Static namespace over the ambient, task-isolated context."""

    # --- visible -------------------------------------------------------------
    @staticmethod
    def add(key: str, value: Any) -> None:
        _visible.set({**_visible_get(), key: value})

    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        return _visible_get().get(key, default)

    @staticmethod
    def all() -> dict[str, Any]:
        return dict(_visible_get())

    @staticmethod
    def forget(key: str) -> None:
        current = _visible_get()
        if key in current:
            updated = dict(current)
            del updated[key]
            _visible.set(updated)

    @staticmethod
    def has(key: str) -> bool:
        return key in _visible_get()

    # --- stacks ----------------------------------------------------------------
    @staticmethod
    def push(key: str, *values: Any) -> None:
        current = _visible_get()
        stack = [*current.get(key, []), *values]
        _visible.set({**current, key: stack})

    @staticmethod
    def pop(key: str) -> Any:
        current = _visible_get()
        stack = current.get(key)
        if not stack:
            return None
        _visible.set({**current, key: stack[:-1]})
        return stack[-1]

    @staticmethod
    def stack_contains(key: str, value: Any) -> bool:
        return value in _visible_get().get(key, [])

    # --- counters ----------------------------------------------------------------
    @staticmethod
    def increment(key: str, amount: int = 1) -> int:
        current = _visible_get()
        new_value: int = current.get(key, 0) + amount
        _visible.set({**current, key: new_value})
        return new_value

    @staticmethod
    def decrement(key: str, amount: int = 1) -> int:
        return Context.increment(key, -amount)

    # --- hidden (never in `all()`) ------------------------------------------------
    @staticmethod
    def add_hidden(key: str, value: Any) -> None:
        _hidden.set({**_hidden_get(), key: value})

    @staticmethod
    def get_hidden(key: str, default: Any = None) -> Any:
        return _hidden_get().get(key, default)

    @staticmethod
    def all_hidden() -> dict[str, Any]:
        return dict(_hidden_get())

    @staticmethod
    def has_hidden(key: str) -> bool:
        return key in _hidden_get()

    # --- scope -------------------------------------------------------------------
    @staticmethod
    @contextmanager
    def scope(**adds: Any) -> Generator[None]:
        """Add `adds` on top of the current visible context for the duration of the block,
        restoring the prior visible + hidden snapshot on exit (success or exception)."""
        visible_snapshot = _visible_get()
        hidden_snapshot = _hidden_get()
        _visible.set({**visible_snapshot, **adds})
        try:
            yield
        finally:
            _visible.set(visible_snapshot)
            _hidden.set(hidden_snapshot)

    # --- dehydrate / hydrate -------------------------------------------------------
    @staticmethod
    def dehydrate() -> ContextPayload:
        # deep-copied so the payload is isolated from the live context (a later push/pop
        # must not mutate an already-captured payload, and vice versa)
        payload: ContextPayload = {
            "visible": copy.deepcopy(_visible_get()),
            "hidden": copy.deepcopy(_hidden_get()),
        }
        for callback in _dehydrating:
            callback(payload)
        return payload

    @staticmethod
    def hydrate(payload: ContextPayload) -> None:
        _visible.set(copy.deepcopy(payload["visible"]))
        _hidden.set(copy.deepcopy(payload["hidden"]))
        for callback in _hydrated:
            callback(payload)

    @staticmethod
    def dehydrating(callback: Callable[[ContextPayload], None]) -> None:
        """Register a callback fired (with the outgoing payload) on every `dehydrate()`."""
        _dehydrating.append(callback)

    @staticmethod
    def hydrated(callback: Callable[[ContextPayload], None]) -> None:
        """Register a callback fired (with the incoming payload) on every `hydrate()`."""
        _hydrated.append(callback)

    @staticmethod
    def flush_callbacks() -> None:
        """Clear every dehydrating/hydrated callback (test hygiene between cases)."""
        _dehydrating.clear()
        _hydrated.clear()
