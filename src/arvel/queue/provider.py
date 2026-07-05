"""QueueServiceProvider — binds the Queue manager (auto-discovered).

Also wires the events ``ShouldQueue`` rail (A2): ``queue_dispatcher`` is the contract seam
``events.Dispatcher`` calls to enqueue a ``ShouldQueue`` listener — events sits below queue in the
module DAG and must not import it directly, so the queue side of the rail is bound here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arvel.kernel.service_provider import ServiceProvider
from arvel.queue import QueueManager

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from arvel.contracts import Container
    from arvel.queue.scheduler import Schedule


class QueueServiceProvider(ServiceProvider):
    def register(self) -> None:
        def make_queue(app: Container) -> QueueManager:
            return QueueManager(app)

        self.app.singleton("queue", make_queue)

        # Bound lazily — Schedule is dependency-light, so scheduling works without a queue broker
        # configured. Threads the app's cache through (when bound) so `on_one_server`/
        # `without_overlapping` coordinate over it without every event reaching for the global
        # `cache()` helper itself; scheduling still works with no cache bound at all (those two
        # features just go unused).
        def make_schedule(app: Container) -> Schedule:
            from arvel.queue.scheduler import Schedule

            cache = app.make("cache") if app.bound("cache") else None
            return Schedule(cache=cache)

        self.app.singleton("schedule", make_schedule)

        def make_queue_dispatcher(
            app: Container,
        ) -> Callable[[Any, tuple[Any, ...]], Awaitable[Any]]:
            async def dispatch_listener(listener: Any, args: tuple[Any, ...]) -> Any:
                from arvel.queue.listener import CallQueuedListener

                job = CallQueuedListener.for_listener(listener, args)
                return await app.make("queue").push_instance(job)

            return dispatch_listener

        self.app.singleton("queue_dispatcher", make_queue_dispatcher)

    def boot(self) -> None:
        """No-op."""
