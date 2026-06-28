"""SearchServiceProvider — binds ``search`` (the SearchManager) for Scout-style indexing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.kernel.service_provider import ServiceProvider
from arvel.search import SearchManager

if TYPE_CHECKING:
    from arvel.contracts import Container


class SearchServiceProvider(ServiceProvider):
    def register(self) -> None:
        def make_search(app: Container) -> SearchManager:
            return SearchManager(app)

        self.app.singleton("search", make_search)

    def boot(self) -> None:
        """No-op."""
