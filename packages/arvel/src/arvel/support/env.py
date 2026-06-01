"""Typed wrapper for environment-variable access.

Typed reads with sensible coercion for bool, int, float, and list values.
"""

from __future__ import annotations

import os
from typing import Literal, TypeVar, overload

T = TypeVar("T", str, int, bool, float, list[str])

_TRUE = frozenset({"true", "1", "yes", "on"})
_FALSE = frozenset({"false", "0", "no", "off"})


class EnvCoercionError(ValueError):
    """Raised when an env value can't be coerced to the type of the supplied default."""


@overload
def env(key: str) -> str | None: ...
@overload
def env(key: str, default: T) -> T: ...
@overload
def env(key: str, *, required: Literal[True]) -> str: ...


def env(  # noqa: C901, PLR0911
    key: str,
    default: object = None,
    *,
    required: bool = False,
) -> object:
    raw = os.environ.get(key)

    if required:
        if raw is None:
            msg = f"Required environment variable {key!r} is not set."
            raise LookupError(msg)
        return raw

    if raw is None:
        return default

    if default is None or isinstance(default, str):
        return raw

    if isinstance(default, bool):
        lowered = raw.strip().lower()
        if lowered in _TRUE:
            return True
        if lowered in _FALSE:
            return False
        msg = f"Env {key!r} is not a recognized boolean (len={len(raw)})."
        raise EnvCoercionError(msg)

    if isinstance(default, int):
        try:
            return int(raw)
        except ValueError as exc:
            msg = f"Env {key!r} is not a valid int (len={len(raw)})."
            raise EnvCoercionError(msg) from exc

    if isinstance(default, float):
        try:
            return float(raw)
        except ValueError as exc:
            msg = f"Env {key!r} is not a valid float (len={len(raw)})."
            raise EnvCoercionError(msg) from exc

    if isinstance(default, list):
        return [piece.strip() for piece in raw.split(",") if piece.strip()]

    msg = f"Unsupported default type {type(default).__name__!r} for env({key!r})."
    raise EnvCoercionError(msg)
