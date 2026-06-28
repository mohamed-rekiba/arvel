"""Configuration repository + the ``config()`` helper.

A stdlib, dotted-key store implementing ``contracts.ConfigRepository`` — pure-Python,
nothing heavy. For *typed* settings, subclass ``arvel.kernel.settings.Settings`` — a typed,
validated **view** over a ``config()`` section, built on **msgspec** (core, no extra; pydantic
is banned — DR-0005/DR-0016). ``env()`` here reads raw environment variables with Laravel-style
literal coercion.

Grounded in knowledge/port/03-application-providers-bootstrap.md + DR-0005/DR-0016.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any, cast

_MISSING: Any = object()

# Laravel-style env literal coercion.
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

    def all(self) -> Mapping[str, Any]:
        """A deep-copy **snapshot** of the whole tree — mutating the result never touches the
        repository (config is read-only at runtime; change it via ``set``)."""
        import copy

        return copy.deepcopy(self._data)

    def __repr__(self) -> str:
        # Redact values: config holds secrets (DB passwords, API keys, tokens). Never let them leak
        # into a repr, traceback, or log line — show only the top-level shape.
        return f"Repository(keys={sorted(self._data)})"


def config(key: str | None = None, default: Any = None) -> Any:
    """Read configuration: ``config()`` → the repository; ``config('app.name')`` → a value."""
    from arvel.kernel.globals import app

    repo = app().make("config")
    return repo if key is None else repo.get(key, default)


def config_default(key: str, fallback: Any) -> Any:
    """Config value for ``key`` when an application (with a ``config`` binding) is running, else
    ``fallback``. Lets light-core components read a configurable default without breaking when
    constructed outside an app (e.g. in tests). Returns ``fallback`` on any resolution failure."""
    import contextlib

    from arvel.kernel.container import BindingResolutionError
    from arvel.kernel.globals import has_application

    if has_application():
        # Swallow only "config isn't resolvable" (no binding / no app), not every error — a genuine
        # bug (e.g. a config value that raises when computed) should surface, not silently become the
        # fallback.
        with contextlib.suppress(LookupError, RuntimeError, BindingResolutionError):
            return config(key, fallback)
    return fallback


def env(key: str, default: Any = None) -> Any:
    """Read an environment variable with Laravel-style literal coercion
    (``true``/``false``/``null``/``empty``); returns ``default`` when unset."""
    raw = os.environ.get(key)
    if raw is None:
        return default
    return _ENV_LITERALS.get(raw.lower(), raw)
