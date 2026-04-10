"""DatabaseEngine — full-text search against the application database.

Supports PostgreSQL tsvector/tsquery and SQLite FTS5.
Falls back to LIKE for unsupported dialects (with a warning).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arvel.search.contracts import SearchEngine

if TYPE_CHECKING:
    from arvel.search.contracts import SearchResult


class DatabaseEngine(SearchEngine):
    """Search engine that queries the application's primary database.

    Inspects the SQLAlchemy engine dialect at init to select the
    correct FTS strategy (PostgreSQL, SQLite, or LIKE fallback).
    """

    async def upsert_documents(
        self,
        index: str,
        documents: list[dict[str, Any]],
        primary_key: str = "id",
    ) -> None: ...

    async def remove_documents(self, index: str, ids: list[str | int]) -> None: ...

    async def search(
        self,
        index: str,
        query: str,
        *,
        filters: dict[str, Any] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> SearchResult:
        raise NotImplementedError("DatabaseEngine.search() is not yet implemented")

    async def flush(self, index: str) -> None: ...

    async def create_index(self, index: str, *, primary_key: str = "id") -> None: ...

    async def delete_index(self, index: str) -> None: ...
