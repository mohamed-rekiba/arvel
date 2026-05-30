"""Type-hint introspection helpers used by the resolution algorithm."""

from __future__ import annotations

import inspect as _inspect
import sys
from collections.abc import Callable
from typing import Any, get_type_hints

_HINT_CACHE: dict[Any, dict[str, type]] = {}


def _collect_stack_locals() -> dict[str, Any]:
    """Merge locals from the call stack so ``get_type_hints`` can resolve
    closure-scoped names (e.g., classes defined inside a test function).

    Walks outward from the caller; earlier frames take precedence on collision.
    """
    merged: dict[str, Any] = {}
    frame: Any = sys._getframe(1)  # pyright: ignore[reportPrivateUsage]
    try:
        while frame is not None:
            for name, value in frame.f_locals.items():
                merged.setdefault(name, value)
            frame = frame.f_back
    finally:
        del frame
    return merged


def init_hints(cls: type) -> dict[str, type]:
    """Return the typed __init__ parameter map for ``cls``, cached per-class."""
    cached = _HINT_CACHE.get(cls)
    if cached is not None:
        return cached

    init_fn: Any = cls.__init__  # type: ignore[misc]
    if init_fn is object.__init__:
        _HINT_CACHE[cls] = {}
        return _HINT_CACHE[cls]

    raw: dict[str, Any]
    try:
        raw = get_type_hints(init_fn)
    except NameError:
        # Closure-scoped types: walk the stack to find them.
        localns = _collect_stack_locals()
        try:
            raw = get_type_hints(init_fn, localns=localns)
        except Exception:  # noqa: BLE001 — last resort
            raw = {}
    except Exception:  # noqa: BLE001 — best-effort: malformed annotation
        raw = {}

    raw.pop("return", None)

    sig = _inspect.signature(init_fn)
    valid = {
        name
        for name, p in sig.parameters.items()
        if name != "self"
        and p.kind not in (_inspect.Parameter.VAR_POSITIONAL, _inspect.Parameter.VAR_KEYWORD)
    }
    cleaned: dict[str, type] = {k: v for k, v in raw.items() if k in valid and isinstance(v, type)}
    _HINT_CACHE[cls] = cleaned
    return cleaned


def is_async_callable(obj: Callable[..., Any]) -> bool:
    return _inspect.iscoroutinefunction(obj)


def is_concrete_class(obj: object) -> bool:
    return isinstance(obj, type)
