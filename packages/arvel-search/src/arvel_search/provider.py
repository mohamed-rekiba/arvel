"""SearchServiceProvider — wires arvel-search into an Arvel app.

Binds ``SearchConfig`` and ``SearchManager``, points the ``Search`` facade at
the manager, and imports the sync jobs so they register with the queue.
``Searchable`` models wire their own lifecycle observers at class-definition
time, so there's nothing to register per-model here.
"""

from __future__ import annotations

from arvel.providers.service_provider import ServiceProvider

from arvel_search.config import SearchConfig
from arvel_search.facade import Search
from arvel_search.manager import SearchManager


class SearchServiceProvider(ServiceProvider):
    """Boot arvel-search inside an Arvel application."""

    def register(self) -> None:
        config = SearchConfig()
        manager = SearchManager(config)
        self.container.instance(SearchConfig, config)
        self.container.instance(SearchManager, manager)

    async def boot(self) -> None:
        from arvel_search import jobs  # noqa: PLC0415 — import registers queue jobs

        _ = jobs  # keep the import meaningful: side-effect is job registration
        Search.bind(self.container.make(SearchManager))


__all__ = ["SearchServiceProvider"]
