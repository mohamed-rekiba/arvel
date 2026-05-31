"""Database engine — full-text-ish search via SQL ILIKE on the source table.

No external server. Writes are no-ops (the data already lives in the table);
reads scan the configured columns with case-insensitive LIKE using bound
parameters — never string-interpolated SQL. Fine for small tables and admin
search boxes; reach for Meilisearch/Elasticsearch at scale.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import or_

from arvel_search.dtos import SearchResult
from arvel_search.engine import Engine
from arvel_search.exceptions import SearchError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from arvel_search.dtos import SearchQuery


class DatabaseEngine(Engine):
    async def upsert_documents(
        self, index: str, documents: Sequence[Mapping[str, Any]], *, key: str
    ) -> None:
        return

    async def remove_documents(self, index: str, keys: Sequence[str]) -> None:
        return

    async def search(self, query: SearchQuery) -> SearchResult:
        model = query.model
        if model is None:
            msg = "DatabaseEngine requires a bound model on the SearchQuery."
            raise SearchError(msg)

        builder = model.query()
        builder = self._apply_term(builder, model, query)
        for column, value in query.filters.items():
            builder = builder.where(getattr(model, column) == value)

        total = await builder.count()

        if query.limit is not None:
            builder = builder.limit(query.limit)
        if query.offset:
            builder = builder.offset(query.offset)

        rows: list[Any] = await builder.get()
        ids = [str(getattr(row, query.key_name)) for row in rows]
        return SearchResult(ids=ids, total=total, raw=rows)

    async def flush(self, index: str) -> None:
        return

    @staticmethod
    def _apply_term(builder: Any, model: type[Any], query: SearchQuery) -> Any:
        if not query.query or not query.columns:
            return builder
        # SQLAlchemy binds the pattern as a parameter — no injection vector.
        pattern = f"%{query.query}%"
        clauses = [getattr(model, column).ilike(pattern) for column in query.columns]
        return builder.where(or_(*clauses))


__all__ = ["DatabaseEngine"]
