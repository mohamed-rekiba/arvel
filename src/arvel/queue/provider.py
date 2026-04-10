"""QueueProvider — wires QueueContract to the configured queue driver."""

from __future__ import annotations

import contextlib
import inspect
from typing import TYPE_CHECKING

from arvel.foundation.config import get_module_settings
from arvel.foundation.container import Scope
from arvel.foundation.provider import ServiceProvider
from arvel.queue.config import QueueSettings
from arvel.queue.contracts import QueueContract
from arvel.queue.manager import QueueManager

if TYPE_CHECKING:
    from arvel.app.config import AppSettings
    from arvel.foundation.application import Application
    from arvel.foundation.container import ContainerBuilder


class QueueProvider(ServiceProvider):
    """Registers queue contract bindings for app-wide reuse."""

    priority = 12

    _settings: QueueSettings | None

    def __init__(self) -> None:
        super().__init__()
        self._settings = None

    def configure(self, config: AppSettings) -> None:
        with contextlib.suppress(Exception):
            self._settings = get_module_settings(config, QueueSettings)

    def _get_settings(self) -> QueueSettings:
        if self._settings is not None:
            return self._settings
        return QueueSettings()

    def _make_queue(self) -> QueueContract:
        settings = self._get_settings()
        manager = QueueManager()
        return manager.create_driver(settings)

    async def register(self, container: ContainerBuilder) -> None:
        container.provide_factory(QueueContract, self._make_queue, scope=Scope.APP)

    async def boot(self, app: Application) -> None:
        pass

    async def shutdown(self, app: Application) -> None:
        try:
            queue = await app.container.resolve(QueueContract)
        except Exception:
            return

        close = getattr(queue, "close", None)
        if callable(close):
            result = close()
            if inspect.isawaitable(result):
                await result
