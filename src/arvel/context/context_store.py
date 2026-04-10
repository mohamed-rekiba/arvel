"""Context store — request-scoped key-value propagation via contextvars.

Provides a unified context that flows through HTTP → logs → queued jobs.
Backed by two ContextVars: one for visible data (included in logs and
serialized for queue propagation) and one for hidden data (excluded from
logs and serialization by default).

See ADR-018-001 for the design rationale (ContextVar[dict] vs per-key).
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, TypeVar, overload

if TYPE_CHECKING:
    from collections.abc import Callable

    _DehydratingHook = Callable[[dict[str, object]], dict[str, object]]
    _HydratedHook = Callable[[dict[str, object]], None]

_T = TypeVar("_T")

_context_data: ContextVar[dict[str, Any]] = ContextVar("arvel_context_data")
_context_hidden: ContextVar[dict[str, Any]] = ContextVar("arvel_context_hidden")

_dehydrating_hooks: list[_DehydratingHook] = []
_hydrated_hooks: list[_HydratedHook] = []

_EMPTY: dict[str, Any] = {}


class Context:
    """Request-scoped context store — static API, no instantiation needed.

    Visible data is merged into structlog log entries and serialized
    alongside queued jobs. Hidden data is never serialized or logged.
    """

    __slots__ = ()

    # ------------------------------------------------------------------
    # Visible context
    # ------------------------------------------------------------------

    @staticmethod
    def add(key: str, value: Any) -> None:
        """Store a key-value pair in the visible context."""
        current = _context_data.get(_EMPTY)
        _context_data.set({**current, key: value})

    @overload
    @staticmethod
    def get(key: str) -> Any: ...

    @overload
    @staticmethod
    def get(key: str, default: _T) -> _T: ...

    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        """Retrieve a value from visible context, or *default* if missing."""
        return _context_data.get(_EMPTY).get(key, default)

    @staticmethod
    def has(key: str) -> bool:
        """Check if *key* exists in visible or hidden context."""
        return key in _context_data.get(_EMPTY) or key in _context_hidden.get(_EMPTY)

    @staticmethod
    def forget(key: str) -> None:
        """Remove *key* from visible context. No-op if missing."""
        current = _context_data.get(_EMPTY)
        if key in current:
            new = {k: v for k, v in current.items() if k != key}
            _context_data.set(new)

    @staticmethod
    def all() -> dict[str, Any]:
        """Return a shallow copy of all visible context data."""
        return dict(_context_data.get(_EMPTY))

    # ------------------------------------------------------------------
    # Hidden context (excluded from logs and serialization)
    # ------------------------------------------------------------------

    @staticmethod
    def add_hidden(key: str, value: Any) -> None:
        """Store a key-value pair in the hidden context (not logged, not serialized)."""
        current = _context_hidden.get(_EMPTY)
        _context_hidden.set({**current, key: value})

    @overload
    @staticmethod
    def get_hidden(key: str) -> Any: ...

    @overload
    @staticmethod
    def get_hidden(key: str, default: _T) -> _T: ...

    @staticmethod
    def get_hidden(key: str, default: Any = None) -> Any:
        """Retrieve a value from hidden context, or *default* if missing."""
        return _context_hidden.get(_EMPTY).get(key, default)

    @staticmethod
    def all_hidden() -> dict[str, Any]:
        """Return a shallow copy of all hidden context data."""
        return dict(_context_hidden.get(_EMPTY))

    # ------------------------------------------------------------------
    # Stack operations
    # ------------------------------------------------------------------

    @staticmethod
    def push(key: str, *values: Any) -> None:
        """Append *values* to a list at *key*. Creates the list if needed.

        If the existing value is not a list, it's wrapped in one first.
        """
        current = _context_data.get(_EMPTY)
        existing = current.get(key)
        if existing is None:
            new_list = list(values)
        elif isinstance(existing, list):
            new_list = [*existing, *values]
        else:
            new_list = [existing, *values]
        _context_data.set({**current, key: new_list})

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @staticmethod
    def flush() -> None:
        """Clear both visible and hidden context stores."""
        _context_data.set({})
        _context_hidden.set({})

    # ------------------------------------------------------------------
    # Dehydration / Hydration (queue propagation)
    # ------------------------------------------------------------------

    @staticmethod
    def dehydrating(callback: _DehydratingHook) -> None:
        """Register a callback that transforms context data before serialization.

        The callback receives the current visible data dict and must return
        a (possibly modified) dict.
        """
        _dehydrating_hooks.append(callback)

    @staticmethod
    def hydrated(callback: _HydratedHook) -> None:
        """Register a callback that runs after context is restored from a serialized dict."""
        _hydrated_hooks.append(callback)

    @staticmethod
    def dehydrate() -> dict[str, Any]:
        """Serialize visible context data for queue propagation.

        Runs all registered ``dehydrating`` callbacks in order. Hidden
        data is NOT included.
        """
        data = dict(_context_data.get(_EMPTY))
        for hook in _dehydrating_hooks:
            data = hook(data)
        return data

    @staticmethod
    def hydrate(data: dict[str, Any]) -> None:
        """Restore context from a serialized dict (e.g. from a queued job).

        Merges *data* into the current visible context, then runs all
        registered ``hydrated`` callbacks in order.
        """
        current = _context_data.get(_EMPTY)
        _context_data.set({**current, **data})
        for hook in _hydrated_hooks:
            hook(data)

    @staticmethod
    def _clear_hooks() -> None:
        """Clear all dehydrating/hydrated hooks. For testing only."""
        _dehydrating_hooks.clear()
        _hydrated_hooks.clear()
