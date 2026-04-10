"""Sentinel value for conditional field omission in API resources.

``MISSING`` marks fields that should be stripped from the response dict
before serialization.  Use identity comparison (``value is MISSING``)
for checks — the singleton is guaranteed unique.
"""

from __future__ import annotations


class _MissingValue:
    """Singleton sentinel — represents a field that should be absent from the response."""

    _instance: _MissingValue | None = None

    def __new__(cls) -> _MissingValue:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "MISSING"

    def __bool__(self) -> bool:
        return False


MISSING: _MissingValue = _MissingValue()
