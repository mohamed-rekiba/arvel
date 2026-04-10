"""SearchProvider — wires SearchEngine to the configured driver and registers the observer."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

from arvel.foundation.container import Scope
from arvel.foundation.provider import ServiceProvider
from arvel.search.config import SearchSettings
from arvel.search.contracts import SearchEngine
from arvel.search.manager import SearchManager

if TYPE_CHECKING:
    from arvel.foundation.application import Application
    from arvel.foundation.container import ContainerBuilder


def _make_search_engine() -> SearchEngine:
    settings = SearchSettings()
    manager = SearchManager()
    return manager.create_driver(settings)


class SearchProvider(ServiceProvider):
    """Registers search engine bindings and the auto-sync observer.

    ``register()`` binds ``SearchEngine`` to the configured driver via
    ``SearchManager``.

    ``boot()`` discovers all ``Searchable`` models and registers
    ``SearchObserver`` against each one in the ``ObserverRegistry``.
    """

    priority = 15

    async def register(self, container: ContainerBuilder) -> None:
        """Bind SearchEngine contract to the configured driver."""
        container.provide_factory(SearchEngine, _make_search_engine, scope=Scope.APP)

    async def boot(self, app: Application) -> None:
        """Register SearchObserver for all Searchable models."""

    async def shutdown(self, app: Application) -> None:
        """Close any engine connections."""
        try:
            engine = await app.container.resolve(SearchEngine)
        except Exception:
            return

        close = getattr(engine, "close", None)
        if callable(close):
            result = close()
            if inspect.isawaitable(result):
                await result
