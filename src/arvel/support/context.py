"""arvel.support.context — an ambient, contextvars-backed key/value store (`Context`
parity), safe across concurrent `asyncio` tasks: each task gets its own copy-on-write snapshot,
so a request/job never sees another's context. Every mutator replaces the backing dict wholesale
rather than mutating it in place — that's what makes the per-task isolation hold.

`Context` is a static namespace (no instances — like `Str`/`Number`). Hidden values
(`add_hidden`/…) never appear in `all()`; every visible operation has a hidden twin backed by
the same `_Channel` implementation. `dehydrate()`/`hydrate()` round-trip the whole state
(visible + hidden) into a plain, msgspec-serializable payload — the caller's contract is that
every stored value serializes; QUEUE-RELIABILITY wires this into job carry-over.
"""

from __future__ import annotations

import contextvars
import copy
from collections.abc import Callable, Generator, Iterable, Mapping
from contextlib import contextmanager
from typing import Any, TypedDict


class ContextPayload(TypedDict):
    """The wire shape produced by `Context.dehydrate()` / consumed by `Context.hydrate()`."""

    visible: dict[str, Any]
    hidden: dict[str, Any]


#: `default=None` (not `{}`) — a mutable default would be one shared dict across every context
#: that never called `.set()`; `_Channel.data()` papers over the `None` case.
_visible: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "arvel_context_visible", default=None
)
_hidden: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "arvel_context_hidden", default=None
)
_dehydrating: list[Callable[[ContextPayload], None]] = []
_hydrated: list[Callable[[ContextPayload], None]] = []


class _Channel:
    """One store (visible or hidden) — every op implemented once, copy-on-write."""

    def __init__(self, var: contextvars.ContextVar[dict[str, Any] | None]) -> None:
        self._var = var

    def data(self) -> dict[str, Any]:
        return self._var.get() or {}

    def replace(self, data: dict[str, Any]) -> None:
        self._var.set(data)

    def add(self, key: str | Mapping[str, Any], value: Any = None) -> None:
        if isinstance(key, Mapping):  # bulk form: `value` has no meaning and is ignored
            self.replace({**self.data(), **key})
        else:
            self.replace({**self.data(), key: value})

    def add_if(self, key: str, value: Any) -> None:
        if key not in self.data():
            self.add(key, value)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data().get(key, default)

    def forget(self, key: str | Iterable[str]) -> None:
        keys = [key] if isinstance(key, str) else list(key)
        current = self.data()
        if any(k in current for k in keys):
            self.replace({k: v for k, v in current.items() if k not in set(keys)})

    def has(self, key: str) -> bool:
        return key in self.data()

    def only(self, keys: Iterable[str]) -> dict[str, Any]:
        keyset = set(keys)
        return {k: v for k, v in self.data().items() if k in keyset}

    def except_(self, keys: Iterable[str]) -> dict[str, Any]:
        keyset = set(keys)
        return {k: v for k, v in self.data().items() if k not in keyset}

    def pull(self, key: str, default: Any = None) -> Any:
        found = self.get(key, default)
        self.forget(key)
        return found

    def push(self, key: str, *values: Any) -> None:
        current = self.data()
        self.replace({**current, key: [*current.get(key, []), *values]})

    def pop(self, key: str) -> Any:
        current = self.data()
        stack = current.get(key)
        if not stack:
            return None
        self.replace({**current, key: stack[:-1]})
        return stack[-1]

    def stack_contains(self, key: str, value: Any) -> bool:
        return value in self.data().get(key, [])


_VISIBLE = _Channel(_visible)
_HIDDEN = _Channel(_hidden)


class Context:
    """Static namespace over the ambient, task-isolated context."""

    # --- visible -------------------------------------------------------------
    @staticmethod
    def add(key: str | Mapping[str, Any], value: Any = None) -> None:
        """Add one key, or every pair of a mapping."""
        _VISIBLE.add(key, value)

    @staticmethod
    def add_if(key: str, value: Any) -> None:
        """Add only when ``key`` is absent."""
        _VISIBLE.add_if(key, value)

    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        return _VISIBLE.get(key, default)

    @staticmethod
    def all() -> dict[str, Any]:
        return dict(_VISIBLE.data())

    @staticmethod
    def forget(key: str | Iterable[str]) -> None:
        """Remove one key or a list of keys; unknown keys are a no-op."""
        _VISIBLE.forget(key)

    @staticmethod
    def has(key: str) -> bool:
        return _VISIBLE.has(key)

    @staticmethod
    def missing(key: str) -> bool:
        return not _VISIBLE.has(key)

    @staticmethod
    def only(keys: Iterable[str]) -> dict[str, Any]:
        return _VISIBLE.only(keys)

    @staticmethod
    def except_(keys: Iterable[str]) -> dict[str, Any]:
        return _VISIBLE.except_(keys)

    @staticmethod
    def pull(key: str, default: Any = None) -> Any:
        """Read ``key`` then remove it — ``pull``."""
        return _VISIBLE.pull(key, default)

    @staticmethod
    def remember(key: str, factory: Callable[[], Any]) -> Any:
        """``get(key)`` if present, else store + return ``factory()`` — ``remember``.
        ``factory`` must be sync; an async callable would store the coroutine itself."""
        if _VISIBLE.has(key):
            return _VISIBLE.get(key)
        resolved = factory()
        _VISIBLE.add(key, resolved)
        return resolved

    @staticmethod
    def when(
        condition: Any,
        then: Callable[[type[Context]], Any],
        otherwise: Callable[[type[Context]], Any] | None = None,
    ) -> None:
        """Invoke ``then(Context)`` if ``condition``, else ``otherwise(Context)`` (if given)."""
        if condition:
            then(Context)
        elif otherwise is not None:
            otherwise(Context)

    # --- stacks ----------------------------------------------------------------
    @staticmethod
    def push(key: str, *values: Any) -> None:
        _VISIBLE.push(key, *values)

    @staticmethod
    def pop(key: str) -> Any:
        return _VISIBLE.pop(key)

    @staticmethod
    def stack_contains(key: str, value: Any) -> bool:
        return _VISIBLE.stack_contains(key, value)

    # --- counters ----------------------------------------------------------------
    @staticmethod
    def increment(key: str, amount: int = 1) -> int:
        current = _VISIBLE.data()
        new_value: int = current.get(key, 0) + amount
        _VISIBLE.replace({**current, key: new_value})
        return new_value

    @staticmethod
    def decrement(key: str, amount: int = 1) -> int:
        return Context.increment(key, -amount)

    # --- hidden (never in `all()`) ------------------------------------------------
    @staticmethod
    def add_hidden(key: str | Mapping[str, Any], value: Any = None) -> None:
        _HIDDEN.add(key, value)

    @staticmethod
    def add_hidden_if(key: str, value: Any) -> None:
        _HIDDEN.add_if(key, value)

    @staticmethod
    def get_hidden(key: str, default: Any = None) -> Any:
        return _HIDDEN.get(key, default)

    @staticmethod
    def all_hidden() -> dict[str, Any]:
        return dict(_HIDDEN.data())

    @staticmethod
    def forget_hidden(key: str | Iterable[str]) -> None:
        _HIDDEN.forget(key)

    @staticmethod
    def has_hidden(key: str) -> bool:
        return _HIDDEN.has(key)

    @staticmethod
    def missing_hidden(key: str) -> bool:
        return not _HIDDEN.has(key)

    @staticmethod
    def only_hidden(keys: Iterable[str]) -> dict[str, Any]:
        return _HIDDEN.only(keys)

    @staticmethod
    def except_hidden(keys: Iterable[str]) -> dict[str, Any]:
        return _HIDDEN.except_(keys)

    @staticmethod
    def pull_hidden(key: str, default: Any = None) -> Any:
        return _HIDDEN.pull(key, default)

    @staticmethod
    def push_hidden(key: str, *values: Any) -> None:
        _HIDDEN.push(key, *values)

    @staticmethod
    def pop_hidden(key: str) -> Any:
        return _HIDDEN.pop(key)

    @staticmethod
    def hidden_stack_contains(key: str, value: Any) -> bool:
        return _HIDDEN.stack_contains(key, value)

    # --- scope -------------------------------------------------------------------
    @staticmethod
    @contextmanager
    def scope(
        data: Mapping[str, Any] | None = None,
        hidden: Mapping[str, Any] | None = None,
        **adds: Any,
    ) -> Generator[None]:
        """Overlay ``data`` (+ any ``**adds`` sugar) on the visible channel and ``hidden`` on
        the hidden channel for the duration of the block, restoring both snapshots on exit
        (success or exception). ``data`` and ``hidden`` are reserved parameter names — a visible
        key literally called either must go through the ``data`` mapping."""
        visible_snapshot = _VISIBLE.data()
        hidden_snapshot = _HIDDEN.data()
        _VISIBLE.replace({**visible_snapshot, **(data or {}), **adds})
        if hidden:
            _HIDDEN.replace({**hidden_snapshot, **hidden})
        try:
            yield
        finally:
            _VISIBLE.replace(visible_snapshot)
            _HIDDEN.replace(hidden_snapshot)

    # --- dehydrate / hydrate -------------------------------------------------------
    @staticmethod
    def dehydrate() -> ContextPayload:
        # deep-copied so the payload is isolated from the live context (a later push/pop
        # must not mutate an already-captured payload, and vice versa)
        payload: ContextPayload = {
            "visible": copy.deepcopy(_VISIBLE.data()),
            "hidden": copy.deepcopy(_HIDDEN.data()),
        }
        for callback in _dehydrating:
            callback(payload)
        return payload

    @staticmethod
    def hydrate(payload: ContextPayload) -> None:
        _VISIBLE.replace(copy.deepcopy(payload["visible"]))
        _HIDDEN.replace(copy.deepcopy(payload["hidden"]))
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
    def flush() -> None:
        """Clear both channels without firing hydrate callbacks (test hygiene between cases)."""
        _VISIBLE.replace({})
        _HIDDEN.replace({})

    @staticmethod
    def flush_callbacks() -> None:
        """Clear every dehydrating/hydrated callback (test hygiene between cases)."""
        _dehydrating.clear()
        _hydrated.clear()
