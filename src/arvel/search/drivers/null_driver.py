"""NullEngine — no-op driver for disabled search (default)."""

from __future__ import annotations

from typing import Any

from arvel.search.contracts import SearchEngine, SearchResult


class NullEngine(SearchEngine):
    """Search engine that silently discards all operations.

    Used when search is disabled (``SEARCH_DRIVER=null``).
    """

    async def upsert_documents(
        self,
        index: str,
        documents: list[dict[str, Any]],
        primary_key: str = "id",
    ) -> None:
        return

    async def remove_documents(self, index: str, ids: list[str | int]) -> None:
        return

    async def search(
        self,
        index: str,
        query: str,
        *,
        filters: dict[str, Any] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> SearchResult:
        return SearchResult(hits=[], total=0)

    async def flush(self, index: str) -> None:
        return

    async def create_index(self, index: str, *, primary_key: str = "id") -> None:
        return

    async def delete_index(self, index: str) -> None:
        return
