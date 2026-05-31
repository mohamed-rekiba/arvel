"""Null engine — swallows writes, returns nothing. The safe default for CI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arvel_search.dtos import SearchResult
from arvel_search.engine import Engine

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from arvel_search.dtos import SearchQuery


class NullEngine(Engine):
    """Indexes nowhere and matches nothing.

    Used when ``SEARCH_DRIVER=null`` — lets apps keep ``Searchable`` models
    without standing up a search server.
    """

    async def upsert_documents(
        self, index: str, documents: Sequence[Mapping[str, Any]], *, key: str
    ) -> None:
        return

    async def remove_documents(self, index: str, keys: Sequence[str]) -> None:
        return

    async def search(self, query: SearchQuery) -> SearchResult:
        return SearchResult(ids=[], total=0, raw=None)

    async def flush(self, index: str) -> None:
        return


__all__ = ["NullEngine"]
