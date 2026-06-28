"""arvel.search — Laravel-Scout-style full-text indexing over a swappable engine.

A ``Searchable`` model is mirrored into a search index on save and removed on delete; querying
goes through the configured engine (``config('search.driver')``, default ``array``). The built-in
``ArrayEngine`` is an in-memory driver (the default + the test driver); ``MeilisearchEngine`` is an
optional driver behind the ``[search]`` extra. Engines are resolved by ``SearchManager`` (the
``arvel.support.manager.Manager`` strategy base). Not part of the original ch-08 port spec — added
on request as a first-party search module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, cast

from arvel.kernel import Settings
from arvel.support.manager import Manager, MissingExtraError


class SearchSettings(Settings):
    """Typed, validated view over the ``search`` config section (DR-0016)."""

    __config_key__ = "search"
    driver: str = "array"  # engine name (open registry → str)


if TYPE_CHECKING:
    from collections.abc import Mapping


class SearchEngine(Protocol):
    """The contract every search driver implements (index/delete/search/flush)."""

    async def index(self, index: str, key: Any, record: dict[str, Any]) -> None: ...
    async def delete(self, index: str, key: Any) -> None: ...
    async def search(self, index: str, query: str) -> list[dict[str, Any]]: ...
    async def flush(self, index: str) -> None: ...


class ArrayEngine:
    """In-memory engine — the default driver and the one used in tests. Search is a naive
    case-insensitive substring match over every value of each indexed record."""

    def __init__(self) -> None:
        self._store: dict[str, dict[Any, dict[str, Any]]] = {}

    async def index(self, index: str, key: Any, record: dict[str, Any]) -> None:
        self._store.setdefault(index, {})[key] = dict(record)

    async def delete(self, index: str, key: Any) -> None:
        self._store.get(index, {}).pop(key, None)

    async def search(self, index: str, query: str) -> list[dict[str, Any]]:
        needle = str(query).lower()
        return [
            record
            for record in self._store.get(index, {}).values()
            if any(needle in str(value).lower() for value in record.values())
        ]

    async def flush(self, index: str) -> None:
        self._store.pop(index, None)


class MeilisearchEngine:
    """Meilisearch-backed engine (optional ``[search]`` extra). Construction fails with
    ``MissingExtraError`` when the ``meilisearch`` client isn't installed."""

    def __init__(self, url: str = "http://localhost:7700", key: str | None = None) -> None:
        try:
            import meilisearch
        except ImportError as exc:  # pragma: no cover - exercised via SearchManager
            raise MissingExtraError("meilisearch", "search") from exc
        self._client = meilisearch.Client(url, key)

    async def index(self, index: str, key: Any, record: dict[str, Any]) -> None:
        self._client.index(index).add_documents([{**record, "_key": key}])

    async def delete(self, index: str, key: Any) -> None:
        self._client.index(index).delete_document(key)

    async def search(self, index: str, query: str) -> list[dict[str, Any]]:
        hits: list[dict[str, Any]] = self._client.index(index).search(query)["hits"]
        return hits

    async def flush(self, index: str) -> None:
        self._client.index(index).delete_all_documents()


class SearchManager(Manager):
    """Resolves the configured search engine. Default driver: ``config('search.driver')`` or
    ``array``. Forwards unknown attributes to the default driver (``Manager`` base)."""

    def default_driver(self) -> str:
        return SearchSettings().driver  # auto-loads + validates config("search")

    def create_array_driver(self) -> ArrayEngine:
        return ArrayEngine()

    def create_meilisearch_driver(self) -> MeilisearchEngine:
        config: Mapping[str, Any] = {}
        if self.app is not None and self.app.bound("config"):
            config = self.app.make("config").get("search.meilisearch", {}) or {}
        return MeilisearchEngine(**config)


class Searchable:
    """Mixin that makes a model searchable (Scout-style): it is indexed on save and removed on
    delete, and ``Model.search(query)`` queries the engine. Override ``to_searchable_array`` to
    control what gets indexed, and ``searchable_as`` to name the index."""

    def to_searchable_array(self) -> dict[str, Any]:
        """The record to index — the model's serialized form by default."""
        data = cast("dict[str, Any]", self.to_dict())  # type: ignore[attr-defined]
        return data

    @classmethod
    def searchable_as(cls) -> str:
        """The index name — the model's table name by default."""
        return str(cls.__table__.name)  # type: ignore[attr-defined]

    def get_search_key(self) -> Any:
        """The index document key — the model's primary key by default."""
        return getattr(self, type(self).__primary_key__)  # type: ignore[attr-defined]

    @staticmethod
    def _search_engine() -> Any:
        from arvel.kernel import app, has_application

        return app("search") if has_application() and app().bound("search") else None

    async def searchable(self) -> None:
        """Index (or re-index) this record now."""
        engine = self._search_engine()
        if engine is not None:
            await engine.index(
                self.searchable_as(), self.get_search_key(), self.to_searchable_array()
            )

    async def unsearchable(self) -> None:
        """Remove this record from the index now."""
        engine = self._search_engine()
        if engine is not None:
            await engine.delete(self.searchable_as(), self.get_search_key())

    @classmethod
    async def search(cls, query: str) -> list[Any]:
        """Search the index and return hydrated models."""
        from arvel.kernel import app

        records = await app("search").search(cls.searchable_as(), query)
        return [cls._hydrate(record) for record in records]  # type: ignore[attr-defined]

    async def _fire(self, hook: str) -> Any:
        result = cast("Any", await super()._fire(hook))  # type: ignore[misc]
        if hook == "saved":
            await self.searchable()
        elif hook == "deleted":
            await self.unsearchable()
        return result


__all__ = [
    "ArrayEngine",
    "MeilisearchEngine",
    "SearchEngine",
    "SearchManager",
    "SearchSettings",
    "Searchable",
]
