"""Search contract — ABC for swappable search engine drivers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SearchHit:
    """A single hit returned by a search engine.

    Attributes:
        id: The primary key value of the matched document.
        score: Relevance score (higher is better). May be 0.0 for
            engines that don't support scoring.
    """

    id: str | int
    score: float = 0.0


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Raw result set returned by ``SearchEngine.search()``.

    Attributes:
        hits: Ordered list of matched document references.
        total: Estimated total matching documents (for pagination).
        raw: Driver-specific metadata (e.g., facet counts, processing time).
    """

    hits: list[SearchHit]
    total: int
    raw: dict[str, Any] = field(default_factory=dict)


class SearchEngine(ABC):
    """Abstract base class for search engine drivers.

    Implementations: NullEngine (no-op), CollectionEngine (in-memory),
    DatabaseEngine (PG tsvector / SQLite FTS5), MeilisearchEngine,
    ElasticsearchEngine.
    """

    @abstractmethod
    async def upsert_documents(
        self,
        index: str,
        documents: list[dict[str, Any]],
        primary_key: str = "id",
    ) -> None:
        """Index or update documents in the given index.

        Each document dict must include a ``primary_key`` field.

        Raises:
            SearchEngineError: If the engine rejects the operation.
        """

    @abstractmethod
    async def remove_documents(
        self,
        index: str,
        ids: list[str | int],
    ) -> None:
        """Remove documents by primary key value.

        Missing IDs are silently ignored (idempotent).

        Raises:
            SearchEngineError: If the engine rejects the operation.
        """

    @abstractmethod
    async def search(
        self,
        index: str,
        query: str,
        *,
        filters: dict[str, Any] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> SearchResult:
        """Execute a full-text search query.

        Args:
            index: Name of the search index.
            query: Search query string.
            filters: Key-value filter constraints applied post-search.
            limit: Maximum number of hits to return.
            offset: Number of hits to skip (for pagination).

        Returns:
            SearchResult with ordered hits, total count, and raw metadata.

        Raises:
            SearchIndexNotFoundError: If the index doesn't exist.
            SearchEngineError: For all other engine failures.
        """

    @abstractmethod
    async def flush(self, index: str) -> None:
        """Remove all documents from the given index.

        The index itself remains; only its contents are cleared.

        Raises:
            SearchIndexNotFoundError: If the index doesn't exist.
        """

    @abstractmethod
    async def create_index(self, index: str, *, primary_key: str = "id") -> None:
        """Create a new search index.

        Does nothing if the index already exists (idempotent).

        Raises:
            SearchEngineError: If the engine rejects the operation.
        """

    @abstractmethod
    async def delete_index(self, index: str) -> None:
        """Delete an index and all its documents.

        Does nothing if the index doesn't exist (idempotent).

        Raises:
            SearchEngineError: If the engine rejects the operation.
        """
