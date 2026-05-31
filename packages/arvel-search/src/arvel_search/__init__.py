"""arvel-search — Scout-style full-text search for Arvel.

Add :class:`Searchable` to a model, declare ``__searchable__``, and records sync
to the configured backend automatically. Query with ``Model.search("term")``.
"""

from __future__ import annotations

from arvel_search.builder import SearchBuilder, SearchPage
from arvel_search.config import SearchConfig
from arvel_search.dtos import SearchQuery, SearchResult
from arvel_search.engine import Engine
from arvel_search.engines import (
    CollectionEngine,
    DatabaseEngine,
    ElasticsearchEngine,
    MeilisearchEngine,
    NullEngine,
)
from arvel_search.exceptions import (
    SearchEngineNotConfigured,
    SearchError,
    UnknownSearchDriverError,
)
from arvel_search.facade import Search
from arvel_search.fake import SearchFake
from arvel_search.manager import SearchManager
from arvel_search.provider import SearchServiceProvider
from arvel_search.searchable import Searchable

__all__ = [
    "CollectionEngine",
    "DatabaseEngine",
    "ElasticsearchEngine",
    "Engine",
    "MeilisearchEngine",
    "NullEngine",
    "Search",
    "SearchBuilder",
    "SearchConfig",
    "SearchEngineNotConfigured",
    "SearchError",
    "SearchFake",
    "SearchManager",
    "SearchPage",
    "SearchQuery",
    "SearchResult",
    "SearchServiceProvider",
    "Searchable",
    "UnknownSearchDriverError",
]
