"""SearchManager — factory that resolves the configured search engine driver."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.foundation.exceptions import ConfigurationError
from arvel.search.config import SearchSettings
from arvel.search.drivers.collection_driver import CollectionEngine
from arvel.search.drivers.null_driver import NullEngine

if TYPE_CHECKING:
    from collections.abc import Callable

    from arvel.search.contracts import SearchEngine


def _make_meilisearch(settings: SearchSettings) -> SearchEngine:
    from arvel.search.drivers.meilisearch_driver import MeilisearchEngine

    return MeilisearchEngine(
        url=settings.meilisearch_url,
        api_key=settings.meilisearch_key,
        timeout=settings.meilisearch_timeout,
    )


def _make_elasticsearch(settings: SearchSettings) -> SearchEngine:
    from arvel.search.drivers.elasticsearch_driver import ElasticsearchEngine

    return ElasticsearchEngine(
        hosts=settings.elasticsearch_hosts,
        verify_certs=settings.elasticsearch_verify_certs,
    )


_BUILTIN_DRIVERS: dict[str, Callable[[SearchSettings], SearchEngine]] = {
    "null": lambda _settings: NullEngine(),
    "collection": lambda _settings: CollectionEngine(),
    "database": lambda _settings: NullEngine(),
    "meilisearch": _make_meilisearch,
    "elasticsearch": _make_elasticsearch,
}


class SearchManager:
    """Resolves the configured ``SearchEngine`` implementation.

    Uses ``SearchSettings.driver`` to pick from built-in drivers
    (``null``, ``collection``, ``database``, ``meilisearch``,
    ``elasticsearch``) or custom-registered ones.
    """

    def __init__(self) -> None:
        self._custom_drivers: dict[str, Callable[[SearchSettings], SearchEngine]] = {}

    def register_driver(self, name: str, factory: Callable[[SearchSettings], SearchEngine]) -> None:
        """Register a custom driver factory by name."""
        self._custom_drivers[name] = factory

    def create_driver(self, settings: SearchSettings | None = None) -> SearchEngine:
        """Build and return the search engine specified by *settings*.

        Raises:
            ConfigurationError: If the driver name is unknown.
            SearchConfigurationError: If a driver's SDK is missing.
        """
        if settings is None:
            settings = SearchSettings()

        name = settings.driver

        if name in self._custom_drivers:
            return self._custom_drivers[name](settings)

        if name in _BUILTIN_DRIVERS:
            return _BUILTIN_DRIVERS[name](settings)

        available = sorted({*_BUILTIN_DRIVERS, *self._custom_drivers})
        raise ConfigurationError(
            f"Unknown search driver {name!r}. Available: {', '.join(available)}"
        )
