"""Configuration repository + the ``config()`` helper.

A stdlib, dotted-key store implementing ``contracts.ConfigRepository`` — pure-Python,
nothing heavy. For *typed* settings, subclass ``arvel.kernel.settings.Settings`` — a typed,
validated **view** over a ``config()`` section, built on **msgspec** (core, no extra; pydantic
is banned — DR-0005/DR-0016). ``env()`` here reads raw environment variables with -style
literal coercion.

Grounded in knowledge/port/03-application-providers-bootstrap.md + DR-0005/DR-0016.
"""

from __future__ import annotations

import builtins
import os
from collections.abc import Mapping
from typing import Any, TypeVar, cast

_MISSING: Any = object()
_T = TypeVar("_T")

# env literal coercion.
_ENV_LITERALS: dict[str, Any] = {
    "true": True,
    "(true)": True,
    "false": False,
    "(false)": False,
    "null": None,
    "(null)": None,
    "empty": "",
    "(empty)": "",
}


class ConfigTypeError(TypeError):
    """A typed getter found a value of the wrong type (or nothing at all)."""

    def __init__(self, key: str, expected: str, value: Any) -> None:
        found = "missing" if value is _MISSING else type(value).__name__
        super().__init__(f"config [{key}] expected {expected}, got {found}")


class Repository:
    """Dotted-key configuration access over a nested ``dict``."""

    def __init__(self, items: Mapping[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = dict(items) if items else {}

    def get(self, key: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in key.split("."):
            if not isinstance(node, dict):
                return default
            node = cast("dict[str, Any]", node).get(part, _MISSING)
            if node is _MISSING:
                return default
        return node

    def set(self, key: str, value: Any) -> None:
        parts = key.split(".")
        node: dict[str, Any] = self._data
        for part in parts[:-1]:
            nxt: Any = node.get(part)
            if not isinstance(nxt, dict):
                if part in node:  # an existing scalar/None is being turned into a section
                    from arvel.kernel.logging import LogManager

                    LogManager().channel("config").debug(
                        "config_set_replacing_scalar_with_section", key=key, part=part
                    )
                nxt = {}
                node[part] = nxt
            node = cast("dict[str, Any]", nxt)
        node[parts[-1]] = value

    def has(self, key: str) -> bool:
        return self.get(key, _MISSING) is not _MISSING

    # --- typed getters: exact type or a loud error, never a silent None ---------
    def string(self, key: str, default: str | None = None) -> str:
        return self._typed(key, default, str)

    def integer(self, key: str, default: int | None = None) -> int:
        return self._typed(key, default, int)

    def float(self, key: str, default: float | None = None) -> float:
        value: Any = self.get(key, _MISSING if default is None else default)
        if type(value) is int:  # ints widen losslessly; bools don't qualify
            return builtins.float(value)
        if type(value) is builtins.float:
            return value
        raise ConfigTypeError(key, "float", value)

    def boolean(self, key: str, default: bool | None = None) -> bool:
        return self._typed(key, default, bool)

    def array(self, key: str, default: list[Any] | None = None) -> list[Any]:
        value: Any = self.get(key, _MISSING if default is None else default)
        if type(value) is list:
            return cast("list[Any]", value)
        if type(value) is tuple:
            return list(cast("tuple[Any, ...]", value))
        raise ConfigTypeError(key, "list", value)

    def _typed(self, key: str, default: _T | None, expected: type[_T]) -> _T:
        value: Any = self.get(key, _MISSING if default is None else default)
        if type(value) is expected:  # exact match: no bool-as-int, no subclass surprises
            return cast("_T", value)
        raise ConfigTypeError(key, expected.__name__, value)

    def all(self) -> Mapping[str, Any]:
        """A deep-copy **snapshot** of the whole tree — mutating the result never touches the
        repository (config is read-only at runtime; change it via ``set``)."""
        import copy

        return copy.deepcopy(self._data)

    def __repr__(self) -> str:
        # config holds secrets (DB passwords, API keys) — never let a value leak into a repr/traceback
        return f"Repository(keys={sorted(self._data)})"


def config(
    key: str | Mapping[str, Any] | None = None,
    default: Any = None,
) -> Any:
    """Configuration access: ``config()`` → the repository; ``config('app.name')`` → a value;
    ``config({'app.name': 'x'})`` → set each dotted key."""
    from arvel.kernel.globals import app

    repo = app().make("config")
    if key is None:
        return repo
    if isinstance(key, Mapping):
        for dotted, value in key.items():
            repo.set(dotted, value)
        return None
    return repo.get(key, default)


def config_default(key: str, fallback: Any) -> Any:
    """Config value for ``key`` when an application (with a ``config`` binding) is running, else
    ``fallback``. Lets light-core components read a configurable default without breaking when
    constructed outside an app (e.g. in tests). Returns ``fallback`` on any resolution failure."""
    import contextlib

    from arvel.kernel.container import BindingResolutionError
    from arvel.kernel.globals import has_application

    if has_application():
        # swallow only "config isn't resolvable" — a genuine bug computing the value should surface
        with contextlib.suppress(LookupError, RuntimeError, BindingResolutionError):
            return config(key, fallback)
    return fallback


def env(key: str, default: Any = None) -> Any:
    """Read an environment variable with literal coercion
    (``true``/``false``/``null``/``empty``); returns ``default`` when unset."""
    raw = os.environ.get(key)
    if raw is None:
        return default
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        return raw[1:-1]  # a quoted value is a literal string — no true/false/null coercion
    return _ENV_LITERALS.get(raw.lower(), raw)
