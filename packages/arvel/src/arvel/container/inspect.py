"""Type-hint introspection helpers used by the resolution algorithm."""

from __future__ import annotations

import inspect as _inspect
import sys
import types
from collections.abc import Callable
from typing import Any, Union, get_args, get_origin, get_type_hints

_HINT_CACHE: dict[Any, dict[str, type]] = {}
_OPTIONAL_PARAMS_CACHE: dict[Any, frozenset[str]] = {}


def _unwrap_optional(hint: Any) -> Any:
    """`X | None` / `Optional[X]` → `X` (single non-None arm); else unchanged.

    A nullable class hint still names a concrete dependency the container can
    build — dropping it (the old `isinstance(v, type)` filter did) meant such
    params were never injected.
    """
    if get_origin(hint) in (Union, types.UnionType):
        non_none = [arg for arg in get_args(hint) if arg is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return hint


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
    cleaned: dict[str, type] = {}
    for name, hint in raw.items():
        if name not in valid:
            continue
        unwrapped = _unwrap_optional(hint)
        if isinstance(unwrapped, type):
            cleaned[name] = unwrapped
    _HINT_CACHE[cls] = cleaned
    return cleaned


def optional_init_params(cls: type) -> frozenset[str]:
    """Names of ``__init__`` params that carry a default value, cached per-class.

    A dependency that can't be resolved is allowed to fall back to this default
    instead of failing the whole build (matches Laravel's optional-dependency
    handling).
    """
    cached = _OPTIONAL_PARAMS_CACHE.get(cls)
    if cached is not None:
        return cached

    init_fn: Any = cls.__init__  # type: ignore[misc]
    if init_fn is object.__init__:
        result = frozenset[str]()
    else:
        sig = _inspect.signature(init_fn)
        result = frozenset(
            name
            for name, p in sig.parameters.items()
            if name != "self" and p.default is not _inspect.Parameter.empty
        )
    _OPTIONAL_PARAMS_CACHE[cls] = result
    return result


def is_async_callable(obj: Callable[..., Any]) -> bool:
    return _inspect.iscoroutinefunction(obj)


def is_concrete_class(obj: object) -> bool:
    return isinstance(obj, type)
