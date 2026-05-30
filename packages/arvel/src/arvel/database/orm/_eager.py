"""Per-instance cache for eager-loaded async pivot relations.

`with_("roles")` on a query builder runs one batched pivot query and stows the
result on each parent here, keyed by attribute name. The `MorphToMany` /
`BelongsToMany` accessors read this cache instead of hitting the DB per parent —
the async equivalent of Eloquent's `setRelation()` after `eagerLoadRelations()`.
"""

from __future__ import annotations

_CACHE_ATTR = "__arvel_eager_relations__"


def set_eager_relation(owner: object, name: str, related: list[object]) -> None:
    """Store a pre-loaded related list on owner under attribute name."""
    cache: dict[str, list[object]] = vars(owner).setdefault(_CACHE_ATTR, {})
    cache[name] = related


def get_eager_relation(owner: object, name: str) -> list[object] | None:
    """Return the cached related list, or None when not eager-loaded."""
    cache: dict[str, list[object]] | None = vars(owner).get(_CACHE_ATTR)
    if cache is None:
        return None
    return cache.get(name)


def clear_eager_relation(owner: object, name: str) -> None:
    """Drop a stale cache entry after a write (attach/detach/sync)."""
    cache: dict[str, list[object]] | None = vars(owner).get(_CACHE_ATTR)
    if cache is not None:
        cache.pop(name, None)
