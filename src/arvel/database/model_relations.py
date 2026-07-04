"""arvel.database.model_relations — ``HasRelationships``: the relation-definition mixin
(``has_many``/``belongs_to``/…/``relation()``, doc 07). Distinct from ``arvel.database.relations``,
which holds the actual ``Relation`` subclasses these methods construct.
"""

from __future__ import annotations

from typing import Any, ClassVar


class HasRelationships:
    """Relation-constructor methods (``has_many``, ``belongs_to``, morph variants, the
    self-referential ``recursive``, …) + ``relation()`` to read an eager-loaded relation.

    The attribute declarations below are a mixin type stub only (see :class:`HasCasts` for why) —
    the real state lives on ``Model``."""

    __primary_key__: ClassVar[str]
    _relations: dict[str, Any]

    def has_many(
        self, related: Any, foreign_key: str | None = None, local_key: str | None = None
    ) -> Any:
        from arvel.database.relations import HasMany
        from arvel.support import Str

        fk = foreign_key or f"{Str.snake(type(self).__name__)}_id"
        return HasMany(self, related, fk, local_key or self.__primary_key__)

    def has_one(
        self, related: Any, foreign_key: str | None = None, local_key: str | None = None
    ) -> Any:
        from arvel.database.relations import HasOne
        from arvel.support import Str

        fk = foreign_key or f"{Str.snake(type(self).__name__)}_id"
        return HasOne(self, related, fk, local_key or self.__primary_key__)

    def belongs_to(
        self, related: Any, foreign_key: str | None = None, owner_key: str | None = None
    ) -> Any:
        from arvel.database.relations import BelongsTo
        from arvel.support import Str

        fk = foreign_key or f"{Str.snake(related.__name__)}_id"
        return BelongsTo(self, related, fk, owner_key or related.__primary_key__)

    def belongs_to_many(
        self,
        related: Any,
        pivot: str | None = None,
        foreign_pivot_key: str | None = None,
        related_pivot_key: str | None = None,
    ) -> Any:
        from arvel.database.relations import BelongsToMany
        from arvel.support import Str

        me = Str.snake(type(self).__name__)
        them = Str.snake(related.__name__)
        pivot = pivot or "_".join(sorted([me, them]))
        return BelongsToMany(
            self,
            related,
            pivot,
            foreign_pivot_key or f"{me}_id",
            related_pivot_key or f"{them}_id",
            self.__primary_key__,
            related.__primary_key__,
        )

    def has_many_through(
        self,
        related: Any,
        through: Any,
        first_key: str | None = None,
        second_key: str | None = None,
    ) -> Any:
        from arvel.database.relations import HasManyThrough
        from arvel.support import Str

        return HasManyThrough(
            self,
            related,
            through,
            first_key or f"{Str.snake(type(self).__name__)}_id",
            second_key or f"{Str.snake(through.__name__)}_id",
            self.__primary_key__,
            through.__primary_key__,
        )

    def has_one_through(
        self,
        related: Any,
        through: Any,
        first_key: str | None = None,
        second_key: str | None = None,
    ) -> Any:
        from arvel.database.relations import HasOneThrough
        from arvel.support import Str

        return HasOneThrough(
            self,
            related,
            through,
            first_key or f"{Str.snake(type(self).__name__)}_id",
            second_key or f"{Str.snake(through.__name__)}_id",
            self.__primary_key__,
            through.__primary_key__,
        )

    def morph_many(self, related: Any, name: str) -> Any:
        from arvel.database.relations import MorphMany

        return MorphMany(self, related, name, self.__primary_key__)

    def morph_one(self, related: Any, name: str) -> Any:
        from arvel.database.relations import MorphOne

        return MorphOne(self, related, name, self.__primary_key__)

    def morph_to(self, name: str) -> Any:
        from arvel.database.relations import MorphTo

        return MorphTo(self, name)

    def morph_to_many(self, related: Any, name: str, pivot: str | None = None) -> Any:
        from arvel.database.relations import MorphToMany

        return MorphToMany(self, related, name, pivot)

    def morphed_by_many(self, related: Any, name: str, pivot: str | None = None) -> Any:
        from arvel.database.relations import MorphedByMany

        return MorphedByMany(self, related, name, pivot)

    def recursive(
        self,
        related: Any,
        foreign_key: str,
        *,
        local_key: str | None = None,
        direction: str = "down",
        depth_key: str = "depth",
    ) -> Any:
        """A self-referential **recursive relation** over an adjacency-list tree. Define it like
        any relation::

            def descendants(self): return self.recursive(Category, "parent_id")
            def ancestors(self):   return self.recursive(Category, "parent_id", direction="up")

        ``.get()`` returns a flat list of models, each carrying a ``depth`` (1 = direct
        child/parent); ``.tree().get()`` returns a nested structure. ``direction="down"`` walks
        children, ``"up"`` walks parents. (For low-level custom recursion use
        ``Builder.recursive_cte`` / ``from_cte``.)"""
        from arvel.database.relations import RecursiveRelation

        return RecursiveRelation(
            self,
            related,
            foreign_key,
            local_key=local_key or self.__primary_key__,
            direction=direction,
            depth_key=depth_key,
        )

    def relation(self, name: str) -> Any:
        """Read an eager-loaded relation (loaded via ``Model.with_(name)``)."""
        return self._relations.get(name)


__all__ = ["HasRelationships"]
