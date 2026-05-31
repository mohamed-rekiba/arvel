"""SearchBuilder — fluent query API returned by ``Model.search(...)``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, TypeVar

from arvel_search.dtos import SearchQuery, SearchResult
from arvel_search.facade import Search

if TYPE_CHECKING:
    from arvel_search.engine import Engine

ModelT = TypeVar("ModelT")


class SearchBuilder(Generic[ModelT]):
    """Builds and runs a search, then hydrates hits back into model instances.

    Cheap and chainable — every ``where``/``limit`` returns ``self``. Nothing
    touches the engine until you await a terminal (:meth:`get`, :meth:`keys`,
    :meth:`raw`, :meth:`count`, :meth:`paginate`). The query string is forwarded
    to the engine as-is — no SQL concatenation, no injection vector.
    """

    def __init__(
        self, model: type[ModelT], query: str = "", *, engine: Engine | None = None
    ) -> None:
        self._model = model
        self._query = query
        self._engine = engine
        self._filters: dict[str, object] = {}
        self._limit: int | None = None
        self._offset = 0

    def where(self, column: str, value: object) -> SearchBuilder[ModelT]:
        self._filters[column] = value
        return self

    def limit(self, limit: int) -> SearchBuilder[ModelT]:
        self._limit = limit
        return self

    def offset(self, offset: int) -> SearchBuilder[ModelT]:
        self._offset = offset
        return self

    async def raw(self) -> SearchResult:
        """Run the search and return the engine's normalized result (no hydration)."""
        return await self._engine_for().search(self._build_query())

    async def keys(self) -> list[str]:
        """Return matching document keys, in relevance order (no DB hydration)."""
        result = await self.raw()
        return result.ids

    async def count(self) -> int:
        """Return the total match count without hydrating records."""
        result = await self.raw()
        return result.total

    async def get(self) -> list[ModelT]:
        """Run the search and hydrate hits into model instances, preserving order."""
        result = await self.raw()
        return await self._hydrate(result.ids)

    async def first(self) -> ModelT | None:
        models = await self.limit(1).get()
        return models[0] if models else None

    async def paginate(self, per_page: int = 15, page: int = 1) -> SearchPage[ModelT]:
        """Offset-paginate. ``page`` is 1-based."""
        self._limit = per_page
        self._offset = (max(page, 1) - 1) * per_page
        result = await self.raw()
        models = await self._hydrate(result.ids)
        return SearchPage(items=models, total=result.total, per_page=per_page, current_page=page)

    def _build_query(self) -> SearchQuery:
        model: Any = self._model
        return SearchQuery(
            index=model.search_index_name(),
            query=self._query,
            limit=self._limit,
            offset=self._offset,
            filters=dict(self._filters),
            model=self._model,
            columns=tuple(model.searchable_columns()),
            key_name=model.search_key_name(),
        )

    def _engine_for(self) -> Engine:
        return self._engine if self._engine is not None else Search.engine()

    async def _hydrate(self, ids: list[str]) -> list[ModelT]:
        if not ids:
            return []
        model: Any = self._model
        key_name = model.search_key_name()
        key_attr = getattr(model, key_name)
        rows: list[ModelT] = await model.query().where_in(key_attr, ids).get()

        order = {key: position for position, key in enumerate(ids)}
        rows.sort(key=lambda row: order.get(str(getattr(row, key_name)), len(order)))
        return rows


class SearchPage(Generic[ModelT]):
    """A page of search hits with offset-pagination metadata."""

    def __init__(
        self, *, items: list[ModelT], total: int, per_page: int, current_page: int
    ) -> None:
        self.items = items
        self.total = total
        self.per_page = per_page
        self.current_page = current_page

    @property
    def last_page(self) -> int:
        if self.per_page <= 0:
            return 1
        return max(1, -(-self.total // self.per_page))

    @property
    def has_more(self) -> bool:
        return self.current_page < self.last_page


__all__ = ["SearchBuilder", "SearchPage"]
