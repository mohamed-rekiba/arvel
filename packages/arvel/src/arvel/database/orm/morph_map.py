"""Polymorphic morph map — stable string aliases for model classes.

ADR-022 stored the *unqualified class name* in ``{name}_type`` (e.g. ``"Post"``).
That token breaks the day someone renames or moves the class. A morph map pins
an explicit alias per model so the stored value survives refactors and
cross-package moves. ADR-145 supersedes the unqualified-name default here.

The map is process-global, mirroring Laravel's ``Relation::morphMap()``. Register
it once at boot::

    from arvel.database import morph_map

    morph_map({"post": Post, "video": Video})

With no argument, :func:`morph_map` returns the current registrations.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from arvel.database.exceptions import ORMError

if TYPE_CHECKING:
    from arvel.database.model import Model


class _MorphState:
    """Process-global morph registry. Mutated in place to avoid `global` rebinds."""

    def __init__(self) -> None:
        self.aliases: dict[str, type[Any]] = {}
        self.strict: bool = False


_state = _MorphState()


class MorphMapError(ORMError):
    """Raised in strict mode (``require_morph_map``) when a model has no alias."""

    def __init__(self, model_name: str) -> None:
        super().__init__(
            f"{model_name} has no morph-map alias but require_morph_map() is on. "
            f"Register it with morph_map({{'<alias>': {model_name}}})."
        )
        self.model_name = model_name


def morph_map(
    mapping: Mapping[str, type[Any]] | None = None, *, merge: bool = True
) -> dict[str, type[Any]]:
    """Register alias→class entries, or return the current map when called bare.

    ``merge=False`` replaces the map instead of extending it.
    """
    if mapping is not None:
        if not merge:
            _state.aliases.clear()
        _state.aliases.update(mapping)
    return dict(_state.aliases)


def require_morph_map(value: bool = True) -> None:
    """Toggle strict mode: using an unmapped model polymorphically raises."""
    _state.strict = value


def morph_map_required() -> bool:
    """Whether strict morph-map mode is on."""
    return _state.strict


def reset_morph_map() -> None:
    """Clear the map and strict flag. For test isolation."""
    _state.aliases.clear()
    _state.strict = False


def get_morph_alias(model_class: type[Any]) -> str:
    """Stored type token for a class: its mapped alias, else the short class name.

    Raises :class:`MorphMapError` when strict mode is on and the class is unmapped.
    """
    for alias, klass in _state.aliases.items():
        if klass is model_class:
            return alias
    if _state.strict:
        raise MorphMapError(model_class.__name__)
    return model_class.__name__


def resolve_morph_class(alias: str) -> type[Model]:
    """Resolve a stored type token back to a model class.

    Checks the morph map first, then falls back to scanning the model registry by
    short class name (the ADR-022 default token). Raises :class:`MorphMapError`
    when nothing matches.
    """
    mapped = _state.aliases.get(alias)
    if mapped is not None:
        return mapped

    from arvel.database.model import Model

    for mapper in Model.registry.mappers:
        klass = mapper.class_
        if klass.__name__ == alias:
            return klass
    raise MorphMapError(alias)


__all__ = [
    "MorphMapError",
    "get_morph_alias",
    "morph_map",
    "morph_map_required",
    "require_morph_map",
    "reset_morph_map",
]
