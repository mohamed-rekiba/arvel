"""Stable polymorphic identity for a model instance: a type token and a key string."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arvel.database.model import Model


def morph_type(instance: Model) -> str:
    """Morph-map alias for the model, falling back to its class name."""
    morph = getattr(type(instance), "get_morph_class", None)
    if callable(morph):
        return str(morph())
    return type(instance).__name__


def model_key(instance: Model) -> str:
    """Primary-key value as a string. Composite keys stringify their tuple."""
    return str(instance.get_key())


__all__ = ["model_key", "morph_type"]
