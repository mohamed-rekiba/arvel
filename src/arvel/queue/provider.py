"""QueueServiceProvider — binds the Queue manager (auto-discovered).

Also wires the events ``ShouldQueue`` rail: the dispatcher (C7) enqueues onto the
``queue`` binding registered here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.kernel.service_provider import ServiceProvider
from arvel.queue import QueueManager

if TYPE_CHECKING:
    from arvel.contracts import Container
    from arvel.queue.scheduler import Schedule


class QueueServiceProvider(ServiceProvider):
    def register(self) -> None:
        def make_queue(app: Container) -> QueueManager:
            return QueueManager(app)

        self.app.singleton("queue", make_queue)

        # Bound lazily — Schedule is dependency-light, so scheduling works without a queue broker configured.
        def make_schedule(_app: Container) -> Schedule:
            from arvel.queue.scheduler import Schedule

            return Schedule()

        self.app.singleton("schedule", make_schedule)

    def boot(self) -> None:
        """No-op."""
