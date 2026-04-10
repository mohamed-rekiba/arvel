"""TaskiqQueue — multi-broker queue driver using Taskiq (optional dependency)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arvel.logging import Log
from arvel.queue.contracts import QueueContract
from arvel.queue.exceptions import QueueConnectionError, QueueError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import timedelta

    from arvel.queue.job import Job

logger = Log.named("arvel.queue.drivers.taskiq_driver")

_TASKIQ_INSTALL_MSG = "taskiq is not installed. Install it with: pip install arvel[taskiq]"


def _require_taskiq() -> Any:
    """Import taskiq or raise a clear error."""
    try:
        import taskiq
    except ImportError:
        raise QueueError(_TASKIQ_INSTALL_MSG) from None
    return taskiq


def create_broker(
    broker_type: str,
    url: str | None = None,
) -> Any:
    """Create a Taskiq broker instance by type.

    Supported: ``redis``, ``nats``, ``rabbitmq``, ``memory``.
    """
    if broker_type == "memory":
        _require_taskiq()
        from taskiq import InMemoryBroker

        return InMemoryBroker()

    if broker_type == "redis":
        try:
            from taskiq_redis import ListQueueBroker
        except ImportError:
            raise QueueError(
                "taskiq-redis is not installed. Install it with: pip install arvel[taskiq]"
            ) from None

        effective_url = url or "redis://localhost:6379"
        return ListQueueBroker(effective_url)

    if broker_type == "nats":
        try:
            from taskiq_nats import NatsBroker
        except ImportError:
            raise QueueError(
                "taskiq-nats is not installed. Install it with: pip install taskiq-nats"
            ) from None

        effective_url = url or "nats://localhost:4222"
        return NatsBroker(effective_url)

    if broker_type == "rabbitmq":
        try:
            from taskiq_aio_pika import AioPikaBroker
        except ImportError:
            raise QueueError(
                "taskiq-aio-pika is not installed. Install it with: pip install taskiq-aio-pika"
            ) from None

        effective_url = url or "amqp://guest:guest@localhost:5672/"
        return AioPikaBroker(effective_url)

    raise QueueError(f"Unknown Taskiq broker type: {broker_type!r}")


class TaskiqQueue(QueueContract):
    """Queue driver backed by Taskiq (multi-broker).

    Requires the ``taskiq`` package: ``pip install arvel[taskiq]``.
    Broker selection (Redis, NATS, RabbitMQ, InMemory) happens at
    construction time via :func:`create_broker`.
    """

    def __init__(
        self,
        broker: Any | None = None,
        *,
        broker_type: str = "redis",
        url: str | None = None,
    ) -> None:
        if broker is not None:
            self._broker = broker
        else:
            self._broker = create_broker(broker_type, url)

    async def dispatch(self, job: Job) -> None:
        _require_taskiq()
        job_data = job.model_dump(mode="json")
        fqn = f"{type(job).__module__}.{type(job).__qualname__}"

        task = self._broker.register_task(
            _taskiq_execute_job,
            task_name=f"arvel.{fqn}",
        )
        try:
            await task.kiq(job_class=fqn, job_data=job_data)
        except Exception as exc:
            raise QueueConnectionError(
                f"Failed to dispatch {type(job).__name__} via Taskiq",
                driver="taskiq",
            ) from exc

        logger.debug("dispatched_job", job=type(job).__name__, driver="taskiq")

    async def later(self, delay: timedelta, job: Job) -> None:
        _require_taskiq()
        job_data = job.model_dump(mode="json")
        fqn = f"{type(job).__module__}.{type(job).__qualname__}"

        task = self._broker.register_task(
            _taskiq_execute_job,
            task_name=f"arvel.{fqn}",
        )
        delay_seconds = int(delay.total_seconds())
        try:
            await task.kiq(
                job_class=fqn,
                job_data=job_data,
                labels={"delay": delay_seconds},
            )
        except Exception as exc:
            raise QueueConnectionError(
                f"Failed to dispatch {type(job).__name__} via Taskiq (delayed)",
                driver="taskiq",
            ) from exc

        logger.debug("dispatched_job", job=type(job).__name__, driver="taskiq", delay=str(delay))

    async def bulk(self, jobs: Sequence[Job]) -> None:
        for job in jobs:
            await self.dispatch(job)

    async def size(self, queue_name: str = "default") -> int:
        return 0

    async def close(self) -> None:
        """Shut down the underlying broker."""
        if hasattr(self._broker, "shutdown"):
            await self._broker.shutdown()


async def _taskiq_execute_job(*, job_class: str, job_data: dict[str, Any]) -> None:
    """Worker-side handler that reconstitutes and runs the job.

    This function is registered with the Taskiq broker as the single task
    entry-point. In a real worker process it would import the job class,
    deserialize ``job_data``, and call ``handle()``.
    """
    import importlib

    module_path, class_name = job_class.rsplit(".", 1)
    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    job = cls.model_validate(job_data)
    await job.handle()
