"""Engine contract — every search driver implements this interface.

Engines are model-agnostic: index writes take plain document dicts and string
keys, never ORM instances. The one exception is the database driver's
:meth:`search`, which reads the bound model off the :class:`SearchQuery` to run
SQL. Hydrating keys back into models is the builder's job, not the engine's.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from arvel_search.dtos import SearchQuery, SearchResult


class Engine(ABC):
    @abstractmethod
    async def upsert_documents(
        self, index: str, documents: Sequence[Mapping[str, Any]], *, key: str
    ) -> None:
        """Index (or re-index) ``documents`` under ``index``.

        ``key`` names the primary-key field inside each document. No-op for an
        empty sequence.
        """

    @abstractmethod
    async def remove_documents(self, index: str, keys: Sequence[str]) -> None:
        """Remove documents with the given keys from ``index``."""

    @abstractmethod
    async def search(self, query: SearchQuery) -> SearchResult:
        """Run a search and return matching document keys, ordered by relevance."""

    @abstractmethod
    async def flush(self, index: str) -> None:
        """Drop every document from ``index`` (keeps the index itself)."""


__all__ = ["Engine"]
