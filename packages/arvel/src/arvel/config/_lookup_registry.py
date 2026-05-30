"""Dotted-key config accessor for the path-loaded config system.

Sits alongside the class-based ``Config.of(SettingsClass)`` accessor; this
one is used by projects that adopt the canonical layout (PRD-004 FR-004-010,
ADR-018) where ``config/*.py`` files declare module-level attributes that
need a dotted lookup at runtime — e.g., ``config('database.DEFAULT')``
resolves to the ``DEFAULT`` attribute on the loaded ``config/database.py``
module.
"""

from __future__ import annotations

import contextlib
import json
import types
from pathlib import Path
from typing import Any, TypeVar, overload

T = TypeVar("T")

# Sentinel — distinguishes "no default supplied" from an explicit None default.
_MISSING: object = object()

# Process-wide registry of loaded config modules, keyed by their file stem.
# Populated by ``ApplicationBuilder.with_config_dir`` during ``.create()``.
# Reset at the start of each ``.create()`` call so two apps in the same
# process see clean state.
_REGISTRY: dict[str, object] = {}


class ConfigKeyError(KeyError):
    """Raised when a dotted config key cannot be resolved.

    Distinct from the stdlib ``KeyError`` so callers can disambiguate
    config-lookup failures from generic dict misses.
    """


def register(stem: str, module: object) -> None:
    """Module-internal: register a loaded config module under ``stem``.

    Not exported via ``arvel.config`` — the parent module is itself prefixed
    with ``_`` to mark it package-private, so the public surface stays clean.
    """
    _REGISTRY[stem] = module


def reset() -> None:
    """Module-internal: clear the registry between independent apps in one process."""
    _REGISTRY.clear()


def lookup(key: str) -> Any:
    """Resolve a dotted config key against the loaded config modules.

    ``key`` is dotted: ``"<module_stem>.<ATTR>[.<sub_attr>...]"``. The first
    segment names the ``config/<stem>.py`` file; subsequent segments
    traverse attribute or subscript access on the result.

    Examples (after ``with_config_dir(p / 'config')`` loaded
    ``config/database.py`` and ``config/app.py``):

    - ``lookup('database.DEFAULT')`` → the ``DEFAULT`` attribute on the
      database module.
    - ``lookup('database.CONNECTIONS.sqlite')`` → the ``sqlite`` entry of
      the ``CONNECTIONS`` dict.
    - ``lookup('app.NAME')`` → the ``NAME`` attribute on the app module.

    Raises ``ConfigKeyError`` if any segment cannot be resolved.
    """
    if not key:
        raise ConfigKeyError("Config key must not be empty")
    segments = key.split(".")
    stem, *rest = segments

    module = _REGISTRY.get(stem)
    if module is None:
        raise ConfigKeyError(
            f"No config module registered for {stem!r}. "
            f"Either with_config_dir(...) was not called, or no config/{stem}.py exists "
            f"(or it starts with '_' and was skipped). "
            f"Registered modules: {sorted(_REGISTRY)!r}.",
        )

    # `cursor` walks an arbitrary dotted path through module attrs and dict keys.
    # Each step's runtime type is genuinely unknown — that's by design for a
    # generic config accessor — so we keep it `Any` and silence pyright's
    # partial-unknown noise per occurrence.
    cursor: Any = module
    walked = [stem]
    for segment in rest:
        # Try attribute access first (module/object), fall back to dict subscript.
        if hasattr(cursor, segment) and not (  # pyright: ignore[reportUnknownArgumentType]
            isinstance(cursor, dict) and segment in cursor
        ):
            cursor = getattr(cursor, segment)  # pyright: ignore[reportUnknownArgumentType]
        elif isinstance(cursor, dict) and segment in cursor:
            cursor = cursor[segment]  # pyright: ignore[reportUnknownVariableType]
        else:
            walked_path = ".".join(walked)
            raise ConfigKeyError(
                f"Cannot resolve {key!r}: no attribute or key {segment!r} on {walked_path}",
            )
        walked.append(segment)

    return cursor  # pyright: ignore[reportUnknownVariableType]


@overload
def config(key: str) -> Any: ...
@overload
def config(key: str, default: T) -> T: ...


def config(key: str, default: object = _MISSING) -> Any:
    """Laravel-style config accessor with optional default.

    Reads from the modules loaded via ``ApplicationBuilder.with_config_dir()``.
    Uses the same dotted-key syntax as ``lookup()``:

    - ``config("app.timezone")``         — returns the value, or ``None`` if not found
    - ``config("app.timezone", "UTC")``  — returns ``"UTC"`` when the key is missing
    - ``config("db.pool_size", 5)``      — default type informs the return type

    Unlike ``lookup()``, this never raises ``ConfigKeyError`` — a missing key
    returns the default (or ``None`` when no default is given).
    """
    try:
        return lookup(key)
    except ConfigKeyError:
        return None if default is _MISSING else default


def _seq_items(seq: Any) -> list[Any]:
    return list(seq)


def _map_items(d: Any) -> list[tuple[Any, Any]]:
    return list(d.items())


def to_jsonable(value: Any) -> Any:
    """Recursively coerce a value to a JSON-serializable primitive.

    Pydantic models go through ``model_dump()``. Anything that can't be
    represented is re-raised as ``TypeError`` so callers can skip it.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in _seq_items(value)]
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in _map_items(value)}
    if hasattr(value, "model_dump"):
        return to_jsonable(value.model_dump())
    raise TypeError(f"Cannot serialize {type(value).__name__!r}")


def _module_to_dict(module: object) -> dict[str, Any]:
    """Return a JSON-serializable snapshot of a module's public attributes."""
    source: dict[str, Any] = {}
    if isinstance(module, types.SimpleNamespace):
        source = vars(module)
    else:
        source = {k: v for k, v in vars(module).items() if not k.startswith("_")}
    result: dict[str, Any] = {}
    for k, v in source.items():
        with contextlib.suppress(TypeError, ValueError):
            result[k] = to_jsonable(v)
    return result


def dump_config_cache(dest: Path) -> int:
    """Serialize the current registry to *dest* and return the number of modules written.

    Creates parent directories as needed. Skips modules with no
    JSON-serializable attributes silently.
    """
    payload: dict[str, dict[str, Any]] = {
        stem: _module_to_dict(module) for stem, module in _REGISTRY.items()
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return len(payload)


def load_from_cache(src: Path) -> bool:
    """Populate the registry from a previously dumped cache file.

    Returns ``True`` on success, ``False`` if the file can't be parsed.
    Does NOT call ``reset()`` first — that's the caller's responsibility.
    """
    try:
        data: dict[str, dict[str, Any]] = json.loads(src.read_text())
    except OSError, json.JSONDecodeError:
        return False
    for stem, attrs in data.items():
        _REGISTRY[stem] = types.SimpleNamespace(**attrs)
    return True
