"""SearchServiceProvider — binds ``search`` (the SearchManager) for Scout-style indexing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.kernel.service_provider import ServiceProvider
from arvel.search import SearchManager, SearchSettings

if TYPE_CHECKING:
    from arvel.contracts import Container


class SearchServiceProvider(ServiceProvider):
    def register(self) -> None:
        def make_search(app: Container) -> SearchManager:
            return SearchManager(app)

        self.app.singleton("search", make_search)

    def boot(self) -> None:
        """When ``search.queue`` is on, register the provided listener so a queued index write
        (``ModelIndexRequested``) still reaches the engine — off the ``Searchable`` save/delete
        call path. A no-op without a bound events dispatcher, or when ``search.queue`` is off
        (the default: inline writes, no listener needed)."""
        if not self.app.bound("events") or not SearchSettings().queue:
            return
        from arvel.search import ModelIndexRequested
        from arvel.search.listeners import handle_index_request

        self.app.make("events").listen(ModelIndexRequested, handle_index_request)
