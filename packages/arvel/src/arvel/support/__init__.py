"""Support primitives — small helpers used across every later subsystem.

Re-exports are lazy (PEP 562). Importing ``arvel.support`` (or a submodule like
``arvel.support.str``, which runs this package init first) must not drag in the
HTTP layer. ``abort``/``abort_if``/``abort_unless`` live in ``http_helpers``,
which pulls ``arvel.http`` → FastAPI; loading them eagerly here made every
``make:*`` CLI command pay the full web-stack import cost.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

# Eager, but stdlib-only and cheap. `env` collides with the `arvel.support.env`
# submodule — a lazy __getattr__ gets shadowed the moment that submodule imports,
# handing back the module instead of the function (same trap as `arvel.config`).
from arvel.support.env import env

if TYPE_CHECKING:
    from arvel.support.annotations import resolve_annotations
    from arvel.support.arr import Arr
    from arvel.support.collections import Collection
    from arvel.support.env import EnvCoercionError
    from arvel.support.http_helpers import abort, abort_if, abort_unless
    from arvel.support.pipeline import Middleware, Next, Pipeline
    from arvel.support.str import Str

_LAZY_EXPORTS: dict[str, str] = {
    "resolve_annotations": "arvel.support.annotations",
    "Arr": "arvel.support.arr",
    "Collection": "arvel.support.collections",
    "EnvCoercionError": "arvel.support.env",
    "abort": "arvel.support.http_helpers",
    "abort_if": "arvel.support.http_helpers",
    "abort_unless": "arvel.support.http_helpers",
    "Middleware": "arvel.support.pipeline",
    "Next": "arvel.support.pipeline",
    "Pipeline": "arvel.support.pipeline",
    "Str": "arvel.support.str",
}


def __getattr__(name: str) -> object:
    module = _LAZY_EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(module), name)


def __dir__() -> list[str]:
    return sorted(__all__)


__all__ = [
    "Arr",
    "Collection",
    "EnvCoercionError",
    "Middleware",
    "Next",
    "Pipeline",
    "Str",
    "abort",
    "abort_if",
    "abort_unless",
    "env",
    "resolve_annotations",
]
