"""Shared mass-assignment helpers used by both ArvelModel and Repository.

Extracted to eliminate duplication — both modules need the same
fillable/guarded column filtering and strict-mode logging.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from arvel.logging import Log

_logger = Log.named("arvel.data.mass_assign")

_TIMESTAMP_COLUMNS = frozenset({"created_at", "updated_at"})


@lru_cache(maxsize=128)
def compute_allowed_columns(model_cls: type) -> frozenset[str]:
    """Compute fillable column names, cached per model class."""
    table = getattr(model_cls, "__table__", None)
    if table is None:
        return frozenset()

    all_cols = {col.name for col in table.columns}
    pk_cols = {col.name for col in table.primary_key.columns}

    fillable: set[str] | None = getattr(model_cls, "__fillable__", None)
    guarded: set[str] | None = getattr(model_cls, "__guarded__", None)

    if fillable is not None:
        return frozenset(fillable & all_cols)
    if guarded is not None:
        return frozenset(all_cols - guarded)
    return frozenset(all_cols - pk_cols - _TIMESTAMP_COLUMNS)


def filter_mass_assignable(model_cls: type, data: dict[str, Any]) -> dict[str, Any]:
    """Strip guarded keys from *data*, warning in strict mode."""
    allowed = compute_allowed_columns(model_cls)
    strict = os.environ.get("ARVEL_STRICT_MASS_ASSIGN", "").lower() in ("1", "true", "yes")
    filtered: dict[str, Any] = {}
    for key, value in data.items():
        if key in allowed:
            filtered[key] = value
        elif strict:
            _logger.warning(
                "Mass-assignment blocked (strict mode): %s.%s",
                model_cls.__name__,
                key,
            )
    return filtered
