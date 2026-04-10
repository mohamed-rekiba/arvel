"""Searchable mixin — opt-in full-text search for ArvelModel subclasses.

Add ``Searchable`` to a model's bases to enable search indexing::

    class User(ArvelModel, Searchable):
        __tablename__ = "users"
        __searchable__ = ["name", "email", "bio"]

Models with ``Searchable`` get a ``search()`` class method and automatic
observer-based sync (index on create/update, remove on delete).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from arvel.search.builder import SearchBuilder


class Searchable:
    """Mixin that marks a model as search-indexable.

    **Class attributes** (set on the model):

    ``__searchable__``
        List of column names to include in the search document.
        Required.

    ``__search_index__``
        Override the index name. Defaults to ``__tablename__``.
    """

    __searchable__: ClassVar[list[str]] = []
    __search_index__: ClassVar[str | None] = None

    id: Any

    @classmethod
    def search_index_name(cls) -> str:
        """Return the search index name for this model.

        Defaults to ``__tablename__`` (or ``__search_index__`` if set).
        """
        if cls.__search_index__:
            return cls.__search_index__
        tablename: str | None = getattr(cls, "__tablename__", None)
        if tablename:
            return tablename
        return cls.__name__.lower()

    @classmethod
    def search(cls, query: str = "") -> SearchBuilder[Any]:
        """Create a search builder for this model.

        Args:
            query: Full-text search query. Empty string matches all.

        Returns:
            A ``SearchBuilder`` bound to this model and the resolved engine.
        """
        from arvel.search.builder import SearchBuilder
        from arvel.search.drivers.null_driver import NullEngine

        engine = NullEngine()
        return SearchBuilder(cls, engine, query, cls.search_index_name())

    def to_searchable_array(self) -> dict[str, Any]:
        """Build the document dict to index.

        Override for custom payloads. Default implementation uses
        ``__searchable__`` column names plus the primary key.
        """
        data: dict[str, Any] = {}
        pk_value = getattr(self, "id", None)
        if pk_value is not None:
            data["id"] = pk_value
        for field in self.__searchable__:
            data[field] = getattr(self, field, None)
        return data

    def searchable_id(self) -> str | int:
        """Return the primary key value used as the document ID."""
        return self.id

    async def search_index(self) -> None:
        """Manually index this model instance in the search engine."""

    async def search_remove(self) -> None:
        """Manually remove this model instance from the search index."""
