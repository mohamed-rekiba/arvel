"""SearchManager — builds the configured engine and caches it."""

from __future__ import annotations

from collections.abc import Callable

from arvel_search.config import SearchConfig
from arvel_search.engine import Engine
from arvel_search.engines import (
    CollectionEngine,
    DatabaseEngine,
    ElasticsearchEngine,
    MeilisearchEngine,
    NullEngine,
)
from arvel_search.exceptions import UnknownSearchDriverError


class SearchManager:
    """Resolves an :class:`Engine` from a :class:`SearchConfig`.

    Engines are built lazily and memoized — one instance per driver name for the
    life of the manager.
    """

    def __init__(self, config: SearchConfig | None = None) -> None:
        self._config = config or SearchConfig()
        self._engines: dict[str, Engine] = {}
        self._factories: dict[str, Callable[[], Engine]] = {
            "null": NullEngine,
            "collection": CollectionEngine,
            "database": DatabaseEngine,
            "meilisearch": self._meilisearch,
            "elasticsearch": self._elasticsearch,
        }

    @property
    def config(self) -> SearchConfig:
        return self._config

    def available_drivers(self) -> list[str]:
        return sorted(self._factories)

    def create_driver(self, name: str | None = None) -> Engine:
        """Return the engine for ``name`` (or the configured default), memoized."""
        driver = name or self._config.driver
        cached = self._engines.get(driver)
        if cached is not None:
            return cached
        factory = self._factories.get(driver)
        if factory is None:
            raise UnknownSearchDriverError(driver, self.available_drivers())
        engine = factory()
        self._engines[driver] = engine
        return engine

    def engine(self, name: str | None = None) -> Engine:
        """Alias for :meth:`create_driver` — reads better at call sites."""
        return self.create_driver(name)

    def register_driver(self, name: str, factory: Callable[[], Engine]) -> None:
        """Register a custom driver. Drops any cached instance under ``name``."""
        self._factories[name] = factory
        self._engines.pop(name, None)

    def _meilisearch(self) -> MeilisearchEngine:
        return MeilisearchEngine(
            host=self._config.meilisearch_url,
            api_key=self._config.meilisearch_key.get_secret_value(),
        )

    def _elasticsearch(self) -> ElasticsearchEngine:
        return ElasticsearchEngine(
            host=self._config.elasticsearch_url,
            api_key=self._config.elasticsearch_key.get_secret_value(),
        )


__all__ = ["SearchManager"]
