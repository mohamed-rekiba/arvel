"""Scope enum used by the container."""

from __future__ import annotations

from enum import StrEnum


class Scope(StrEnum):
    """Lifetime of a binding's resolved instance."""

    SINGLETON = "singleton"
    SCOPED = "scoped"
    TRANSIENT = "transient"
