"""arvel.database.collection — ``EloquentCollection[M]``: the model-aware result set returned by
``Builder.get()`` (hydrating) and relation ``get()`` (Laravel Eloquent Collection parity, doc B3).

Subclasses ``arvel.support.Collection`` (support sits below database in the layered DAG — G1) so
the full fluent Collection surface (``map``/``filter``/``pluck``/``where``/…) comes along for
free, and additionally implements ``collections.abc.Sequence`` directly (``__getitem__`` +
``Collection``'s existing ``__iter__``/``__len__``) — this is the return-type change from a plain
``list`` (doc B3): existing callers doing list-style iteration/indexing/``len()``, or an
``isinstance(x, Sequence)`` check, keep working. Adds model-aware batch operations on top:
``load``/``load_missing`` (batched eager-load reusing ``Builder._eager_load_path``, so no N+1),
``model_keys``/``find``/``contains``, ``fresh`` (one batched re-query via ``to_query``),
``make_hidden``/``make_visible`` (fan to every member), ``to_dict``/``to_json``, ``only``/
``except_`` (filter by primary key), and ``to_query`` (a fresh ``WHERE pk IN (...)`` builder over
these members — Laravel ``toQuery``).

**Divergence from Laravel:** a raw (non-hydrating) table-builder ``get()`` — no model bound —
still returns a plain ``list[dict]``; only *hydrated* results become an ``EloquentCollection``.
Transformations that build a NEW collection from arbitrary values (``map``/``filter``/…, inherited
from the base ``Collection``) return a plain ``Collection``, not ``EloquentCollection`` — the
callback's output isn't guaranteed to still be models, so re-wrapping would be misleading.
"""

from __future__ import annotations

import json
from collections.abc import Sequence as _Sequence
from typing import TYPE_CHECKING, Any, cast

from arvel.support import Collection

if TYPE_CHECKING:
    from collections.abc import Iterable

    from arvel.database.builder import Builder

_UNSET: Any = object()  # sentinel: distinguishes "no value given" from a real `None`/falsy value


class EloquentCollection[M](Collection[M], _Sequence[M]):
    """A ``Collection`` of hydrated models, with Eloquent-collection batch operations. ``M`` is
    an unbound TypeVar (any hydrated model), so member attribute access below goes through
    ``Any`` — the same dynamic-attribute-access posture ``Model`` itself uses (doc 07)."""

    def __getitem__(self, index: Any) -> Any:
        if isinstance(index, slice):
            return EloquentCollection(self._items[index])
        return cast("Any", self._items[index])

    def __eq__(self, other: object) -> bool:
        """Also compares equal to a plain ``list`` of the same items — ergonomic parity for
        code (old and new) that checks an empty/expected result against a list literal."""
        if isinstance(other, list):
            return self.all() == other
        return super().__eq__(other)

    __hash__ = None  # type: ignore[assignment]  # unhashable, same posture as the base Collection

    def count(self, value: Any = _UNSET) -> int:
        """Item count (Laravel ``count()``, the base ``Collection`` behavior); also satisfies
        ``collections.abc.Sequence.count``: given a ``value``, counts its occurrences instead."""
        if value is _UNSET:
            return len(self._items)
        return sum(1 for x in self._items if x == value)

    @staticmethod
    def _pk(model: Any) -> Any:
        model_cls = cast("Any", type(model))
        return model._attributes.get(model_cls.__primary_key__)

    def _model_cls(self) -> Any:
        return type(self._items[0])

    def model_keys(self) -> list[Any]:
        """The primary key of every member, in order (Laravel ``modelKeys``)."""
        return [self._pk(m) for m in self._items]

    def find(self, key: Any, default: M | None = None) -> M | None:
        """The member whose primary key equals ``key``, else ``default`` (Laravel ``find``)."""
        for model in self._items:
            if self._pk(model) == key:
                return model
        return default

    def contains(self, item: Any) -> bool:
        """Whether ``item`` — a member (by primary key) OR a bare key — is present (Laravel
        Eloquent Collection ``contains``, a key-aware variant of the base ``Collection.contains``)."""
        if self._items and isinstance(item, type(self._items[0])):
            return self.find(self._pk(item)) is not None
        return self.find(item) is not None

    async def load(self, *relations: str) -> EloquentCollection[M]:
        """Batch eager-load ``relations`` across every member — one ``WHERE IN`` per relation, no
        N+1 (Laravel ``load``). Reuses ``Builder._eager_load_path``, the same machinery
        ``Model.with_(...)`` uses."""
        if not self._items:
            return self
        from arvel.database.builder import Builder

        loader = Builder(self._model_cls().__table__)
        for spec in relations:
            await loader._eager_load_path(  # pyright: ignore[reportPrivateUsage]
                list(self._items), spec.split(".")
            )
        return self

    async def load_missing(self, *relations: str) -> EloquentCollection[M]:
        """Like :meth:`load`, but only for relations not already loaded on every member
        (Laravel ``loadMissing``)."""
        missing = [name for name in relations if not self._all_loaded(name.split(".")[0])]
        if missing:
            await self.load(*missing)
        return self

    def _all_loaded(self, name: str) -> bool:
        return all(name in getattr(m, "_relations", {}) for m in self._items)

    async def fresh(self) -> EloquentCollection[M]:
        """Reload every member from the database in ONE batched query (Laravel ``fresh``);
        members deleted since they were fetched are silently dropped."""
        if not self._items:
            return EloquentCollection()
        fresh_rows = await self.to_query().get()
        by_key = {self._pk(m): m for m in fresh_rows}
        return EloquentCollection([by_key[key] for key in self.model_keys() if key in by_key])

    def make_hidden(self, *keys: str) -> EloquentCollection[M]:
        """Hide ``keys`` on every member's serialization (fans ``Model.make_hidden``)."""
        for m in self._items:
            cast("Any", m).make_hidden(*keys)
        return self

    def make_visible(self, *keys: str) -> EloquentCollection[M]:
        """Reveal ``keys`` on every member's serialization (fans ``Model.make_visible``)."""
        for m in self._items:
            cast("Any", m).make_visible(*keys)
        return self

    def to_dict(self) -> list[dict[str, Any]]:
        return [cast("Any", m).to_dict() for m in self._items]

    def to_json(self, **kwargs: Any) -> str:
        from arvel.database.model_casts import json_default

        return json.dumps(self.to_dict(), default=json_default, **kwargs)

    def only(self, keys: Iterable[Any]) -> EloquentCollection[M]:
        """Members whose primary key is in ``keys`` (Laravel Eloquent Collection ``only`` —
        keyed by primary key, unlike the base ``Collection`` which has no such method)."""
        allowed = list(keys)
        return EloquentCollection([m for m in self._items if self._pk(m) in allowed])

    def except_(self, keys: Iterable[Any]) -> EloquentCollection[M]:
        """Members whose primary key is NOT in ``keys`` (Laravel ``except``)."""
        blocked = list(keys)
        return EloquentCollection([m for m in self._items if self._pk(m) not in blocked])

    def to_query(self) -> Builder:
        """A fresh ``Builder`` constrained to ``WHERE pk IN (these members' keys)`` — Laravel
        ``toQuery()``. Requires a non-empty collection to resolve the model class."""
        if not self._items:
            raise RuntimeError("to_query() requires a non-empty EloquentCollection.")
        model_cls = self._model_cls()
        result: Builder = model_cls.where_in(model_cls.__primary_key__, self.model_keys())
        return result


__all__ = ["EloquentCollection"]
