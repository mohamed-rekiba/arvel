"""SearchProvider — wires SearchEngine to the configured driver and registers the observer."""

from __future__ import annotations

import contextlib
import inspect
from typing import TYPE_CHECKING

from arvel.foundation.config import get_module_settings
from arvel.foundation.container import Scope
from arvel.foundation.provider import ServiceProvider
from arvel.search.config import SearchSettings
from arvel.search.contracts import SearchEngine
from arvel.search.manager import SearchManager

if TYPE_CHECKING:
    from arvel.app.config import AppSettings
    from arvel.foundation.application import Application
    from arvel.foundation.container import ContainerBuilder


class SearchProvider(ServiceProvider):
    """Binds SearchEngine and auto-syncs Searchable models via observer."""

    priority = 15

    _settings: SearchSettings | None

    def __init__(self) -> None:
        super().__init__()
        self._settings = None

    def configure(self, config: AppSettings) -> None:
        with contextlib.suppress(Exception):
            self._settings = get_module_settings(config, SearchSettings)

    def _get_settings(self) -> SearchSettings:
        if self._settings is not None:
            return self._settings
        return SearchSettings()

    def _make_search_engine(self) -> SearchEngine:
        settings = self._get_settings()
        manager = SearchManager()
        return manager.create_driver(settings)

    async def register(self, container: ContainerBuilder) -> None:
        container.provide_factory(SearchEngine, self._make_search_engine, scope=Scope.APP)

    async def boot(self, app: Application) -> None:
        pass

    async def shutdown(self, app: Application) -> None:
        try:
            engine = await app.container.resolve(SearchEngine)
        except Exception:
            return

        close = getattr(engine, "close", None)
        if callable(close):
            result = close()
            if inspect.isawaitable(result):
                await result
