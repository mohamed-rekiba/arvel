"""Full-text search — Scout-style model search with swappable engines."""

from arvel.search.builder import PaginatedSearchResult as PaginatedSearchResult
from arvel.search.builder import SearchBuilder as SearchBuilder
from arvel.search.config import SearchSettings as SearchSettings
from arvel.search.contracts import SearchEngine as SearchEngine
from arvel.search.contracts import SearchHit as SearchHit
from arvel.search.contracts import SearchResult as SearchResult
from arvel.search.exceptions import SearchConfigurationError as SearchConfigurationError
from arvel.search.exceptions import SearchConnectionError as SearchConnectionError
from arvel.search.exceptions import SearchEngineError as SearchEngineError
from arvel.search.exceptions import SearchIndexNotFoundError as SearchIndexNotFoundError
from arvel.search.manager import SearchManager as SearchManager
from arvel.search.mixin import Searchable as Searchable
from arvel.search.observer import SearchObserver as SearchObserver
from arvel.search.provider import SearchProvider as SearchProvider

__all__ = [
    "PaginatedSearchResult",
    "SearchBuilder",
    "SearchConfigurationError",
    "SearchConnectionError",
    "SearchEngine",
    "SearchEngineError",
    "SearchHit",
    "SearchIndexNotFoundError",
    "SearchManager",
    "SearchObserver",
    "SearchProvider",
    "SearchResult",
    "SearchSettings",
    "Searchable",
]
