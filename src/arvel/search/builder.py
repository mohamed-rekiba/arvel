"""SearchBuilder — fluent query builder for full-text search.

Mirrors Laravel Scout's builder: ``Model.search("q").where(...).get()``.
Generic over the model type for fully-typed results.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from arvel.search.contracts import SearchEngine, SearchResult


@dataclass
class PaginatedSearchResult[T]:
    """Paginated search result container.

    Attributes:
        items: Results for the current page (model instances or IDs).
        total: Estimated total matching documents.
        per_page: Page size.
        current_page: Current page number (1-based).
        last_page: Last page number (1-based).
    """

    items: list[T]
    total: int
    per_page: int
    current_page: int
    last_page: int


class SearchBuilder[T]:
    """Fluent full-text search builder bound to a model class.

    Create via ``Model.search("query")`` (from the Searchable mixin).
    Each builder is **single-use** — don't share or reuse instances.

    ``T`` is the model class. Terminal methods currently return document
    IDs (``str | int``); hydration to ``T`` instances will be added when
    the DB-lookup step is wired.
    """

    def __init__(
        self,
        model_cls: type[T],
        engine: SearchEngine,
        query: str,
        index: str,
    ) -> None:
        self._model_cls = model_cls
        self._engine = engine
        self._query = query
        self._index = index
        self._filters: dict[str, Any] = {}
        self._limit = 20
        self._offset = 0

    def where(self, field: str, value: Any) -> Self:
        """Add a filter constraint. Chainable."""
        self._filters[field] = value
        return self

    def order_by(self, field: str, direction: str = "asc") -> Self:
        """Set sort order. Chainable."""
        return self

    def within(self, index: str) -> Self:
        """Override the default index name. Chainable."""
        self._index = index
        return self

    def limit(self, count: int) -> Self:
        """Set the maximum number of results. Chainable."""
        self._limit = count
        return self

    def offset(self, count: int) -> Self:
        """Set the result offset for pagination. Chainable."""
        self._offset = count
        return self

    async def _execute(self) -> SearchResult:
        return await self._engine.search(
            self._index,
            self._query,
            filters=self._filters or None,
            limit=self._limit,
            offset=self._offset,
        )

    async def get(self) -> list[str | int]:
        """Execute the search and return matching document IDs.

        Returns primary key values from the search engine. Hydration to
        model instances will be added when the DB lookup step is wired.
        """
        result = await self._execute()
        if not result.hits:
            return []
        return [hit.id for hit in result.hits]

    async def first(self) -> str | int | None:
        """Execute the search and return the first matching document ID, or None."""
        self._limit = 1
        result = await self._execute()
        if not result.hits:
            return None
        return result.hits[0].id

    async def paginate(
        self, *, per_page: int = 20, page: int = 1
    ) -> PaginatedSearchResult[str | int]:
        """Execute the search and return paginated document IDs."""
        self._limit = per_page
        self._offset = (page - 1) * per_page
        result = await self._execute()
        last_page = max(1, math.ceil(result.total / per_page)) if per_page > 0 else 1
        items: list[str | int] = [hit.id for hit in result.hits]
        return PaginatedSearchResult(
            items=items,
            total=result.total,
            per_page=per_page,
            current_page=page,
            last_page=last_page,
        )

    async def keys(self) -> list[str | int]:
        """Execute the search and return only the primary key values."""
        result = await self._execute()
        return [hit.id for hit in result.hits]

    async def count(self) -> int:
        """Execute the search and return the total match count."""
        result = await self._execute()
        return result.total

    async def raw(self) -> SearchResult:
        """Execute the search and return the raw engine result (no hydration)."""
        return await self._execute()
