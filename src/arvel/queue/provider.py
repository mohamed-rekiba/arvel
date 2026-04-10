"""QueueProvider — wires QueueContract to the configured queue driver."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

from arvel.foundation.container import Scope
from arvel.foundation.provider import ServiceProvider
from arvel.queue.config import QueueSettings
from arvel.queue.contracts import QueueContract
from arvel.queue.manager import QueueManager

if TYPE_CHECKING:
    from arvel.foundation.application import Application
    from arvel.foundation.container import ContainerBuilder


def _make_queue() -> QueueContract:
    settings = QueueSettings()
    manager = QueueManager()
    return manager.create_driver(settings)


class QueueProvider(ServiceProvider):
    """Registers queue contract bindings for app-wide reuse."""

    priority = 12

    async def register(self, container: ContainerBuilder) -> None:
        container.provide_factory(QueueContract, _make_queue, scope=Scope.APP)

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
