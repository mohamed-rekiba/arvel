"""Taskiq driver — delegates to a Taskiq broker chosen by ``broker_url`` scheme.

WI-018 (ADR-067): the broker module is picked by the URL scheme of
``TaskiqQueueConfig.broker_url``. ``redis://``/``rediss://``/``unix://`` →
``taskiq_redis.ListQueueBroker``; ``amqp://``/``amqps://`` →
``taskiq_aio_pika.AioPikaBroker`` (declared with ``max_priority=9`` so
RabbitMQ honours per-message priority natively).

Per-message priority on the Redis broker is routed via queue-name suffix
``<base>:p<N>`` because ``taskiq-redis``'s ``ListQueueBroker`` has no
native priority. Operators run ``taskiq worker arvel:p9 arvel:p8 ...
arvel:p0`` to drain in priority order. See ADR-067 for the trade-off.
"""

from __future__ import annotations

import importlib
import uuid
from typing import Any, Final, Protocol, cast
from urllib.parse import urlparse

from arvel.logging.facade import Log
from arvel.queue.config import TaskiqQueueConfig
from arvel.queue.envelope import JobEnvelope

logger = Log.channel(__name__)


class _TaskiqBroker(Protocol):
    """Minimal interface of taskiq brokers used by ``TaskiqConnection``."""

    async def startup(self) -> None: ...
    async def kick(self, message: Any) -> None: ...
    async def listen(self) -> Any: ...
    async def shutdown(self) -> None: ...


# Scheme → (broker module, extra name) used by both select_broker_module
# and the ImportError messages so the install command stays in sync.
_BROKER_BY_SCHEME: Final[dict[str, tuple[str, str]]] = {
    "redis": ("taskiq_redis", "queue-redis"),
    "rediss": ("taskiq_redis", "queue-redis"),
    "unix": ("taskiq_redis", "queue-redis"),
    "amqp": ("taskiq_aio_pika", "queue-amqp"),
    "amqps": ("taskiq_aio_pika", "queue-amqp"),
}


def select_broker_module(broker_url: str) -> tuple[str, str]:
    """Map a broker URL scheme to ``(module_name, extra_name)``.

    Raises ``ValueError`` for unknown schemes. The message echoes the bad
    scheme so operators can fix their config without reading code. Public
    because tests need to assert routing without instantiating a real
    broker connection.
    """
    scheme = urlparse(broker_url).scheme
    if not scheme or scheme not in _BROKER_BY_SCHEME:
        raise ValueError(
            f"Unsupported queue broker scheme: {scheme!r}. Supported: {sorted(_BROKER_BY_SCHEME)}."
        )
    return _BROKER_BY_SCHEME[scheme]


class TaskiqConnection:
    """Queue driver backed by a Taskiq broker; broker chosen by URL scheme."""

    def __init__(self, config: TaskiqQueueConfig) -> None:
        self._config = config
        self._broker: _TaskiqBroker | None = None
        self._started: bool = False

    async def _get_broker(self) -> _TaskiqBroker:
        if self._broker is None:
            module_name, extra_name = select_broker_module(self._config.broker_url)
            try:
                module = importlib.import_module(module_name)
            except ImportError as exc:
                # NFR-018-05: include only the missing package + install command;
                # no stack chaining, no path leak.
                raise ImportError(
                    f"arvel requires '{module_name.replace('_', '-')}'. "
                    f"Install with: pip install arvel[{extra_name}]"
                ) from exc
            self._broker = self._construct_broker(module, module_name)
        if not self._started:
            # AioPikaBroker requires startup() before kick(); ListQueueBroker
            # tolerates redundant startup. Cache the started state so we only
            # incur the connection cost once per TaskiqConnection.
            await self._broker.startup()
            self._started = True
        return self._broker

    def _construct_broker(self, module: Any, module_name: str) -> _TaskiqBroker:
        if module_name == "taskiq_redis":
            return cast("_TaskiqBroker", module.ListQueueBroker(url=self._config.broker_url))
        # taskiq_aio_pika.AioPikaBroker — declare queue with max_priority=9 so
        # RabbitMQ honours per-message priority (FR-018-11 amqp branch).
        return cast(
            "_TaskiqBroker",
            module.AioPikaBroker(url=self._config.broker_url).with_max_priority(9)
            if hasattr(module.AioPikaBroker, "with_max_priority")
            else module.AioPikaBroker(url=self._config.broker_url, max_priority=9),
        )

    async def push(self, envelope: JobEnvelope, queue: str = "default") -> None:
        broker = await self._get_broker()
        target_queue = self._route_queue(queue, envelope)
        _taskiq_message = importlib.import_module("taskiq.message")
        # Only set labels when non-default — taskiq_aio_pika treats the
        # presence of a `delay` label as "route via delay exchange" even if
        # delay==0, which fails unless the operator installed the
        # rabbitmq-delayed-message-exchange plugin.
        labels: dict[str, Any] = {}
        if envelope.delay > 0:
            labels["delay"] = envelope.delay
        if envelope.priority > 0:
            labels["priority"] = envelope.priority
        if target_queue != "default":
            labels["queue_name"] = target_queue
        msg = _taskiq_message.BrokerMessage(
            task_id=str(uuid.uuid4()),
            task_name=envelope.job_class,
            message=envelope.to_json().encode(),
            labels=labels,
        )
        try:
            await broker.kick(msg)
        except Exception as exc:
            self._raise_with_amqp_hint_if_relevant(exc, envelope)
            raise

    def _raise_with_amqp_hint_if_relevant(self, exc: BaseException, envelope: JobEnvelope) -> None:
        """Surface an actionable error when AMQP delay routing fails.

        ``taskiq_aio_pika`` raises ``IncorrectRoutingKeyError`` with the
        text "Delay requested but no delay queue or delayed-message-exchange
        is configured in the broker" when a delay > 0 is dispatched and the
        delayed-message-exchange plugin is not installed. The upstream
        message is correct but doesn't tell operators how to fix it; this
        helper re-raises as a ``RuntimeError`` carrying the install command.
        """
        if envelope.delay <= 0:
            return
        message = str(exc)
        if "delay queue" not in message and "delayed-message-exchange" not in message:
            return
        raise RuntimeError(
            "AMQP per-message delay requires the rabbitmq-delayed-message-exchange "
            "plugin. Install with: rabbitmq-plugins enable "
            "rabbitmq_delayed_message_exchange. Alternative: omit job.delay and "
            "schedule dispatch from your application."
        ) from exc

    def _route_queue(self, base_queue: str, envelope: JobEnvelope) -> str:
        """Return the broker-side queue name for an envelope.

        For the AMQP broker we always use the base queue name (priority is
        carried by ``BrokerMessage.labels`` and honoured by the AMQP queue
        declaration). For the Redis broker we route by ``:p<N>`` suffix so
        operators can drain by priority (ADR-067).
        """
        module_name, _ = select_broker_module(self._config.broker_url)
        if module_name == "taskiq_redis" and envelope.priority > 0:
            # `default` is the Taskiq broker's own default queue name — when
            # arvel pushes to its own "default" we let Taskiq keep its name
            # and only add the priority suffix.
            broker_queue = "taskiq" if base_queue == "default" else base_queue
            return f"{broker_queue}:p{envelope.priority}"
        return base_queue

    async def pop_blocking(
        self, queue: str = "default", timeout: float = 3.0
    ) -> JobEnvelope | None:
        broker = await self._get_broker()
        msg = await broker.listen()
        if msg is None:
            return None
        try:
            raw: bytes = msg.data
            return JobEnvelope.from_json(raw.decode())
        except (ValueError, TypeError) as exc:
            logger.warning(
                "queue.envelope.malformed",
                driver="taskiq",
                queue=queue,
                payload_size=len(msg.data) if hasattr(msg, "data") else 0,
                exception_type=type(exc).__name__,
                reason=str(exc),
            )
            return None

    async def size(self, queue: str = "default") -> int:
        return 0

    async def clear(self, queue: str = "default") -> None:
        pass

    async def close(self) -> None:
        if self._broker is not None:
            await self._broker.shutdown()
            self._broker = None
            self._started = False


__all__ = ["TaskiqConnection"]
