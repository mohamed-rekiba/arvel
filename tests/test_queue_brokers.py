"""Queue — config-driven broker selection (memory / redis / amqp). The QueueManager builds its taskiq
broker from the ``queue`` config (``default`` names the driver); redis needs ``[queue-redis]``, amqp
needs ``[queue-amqp]``. Brokers construct without connecting (connect happens on startup)."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.queue import QueueManager, QueueSettings


def _app_with_queue_config(**queue: Any) -> Any:
    from arvel.kernel import Application, set_application

    app = Application()
    app.make("config").set("queue", queue)
    set_application(app)
    return app


def test_default_driver_is_in_memory() -> None:
    from taskiq import InMemoryBroker

    assert QueueSettings().default == "memory"
    assert isinstance(QueueManager().broker, InMemoryBroker)  # no app/config → memory


def test_redis_driver_builds_a_redis_broker() -> None:
    from taskiq_redis import ListQueueBroker

    from arvel.kernel import set_application

    app = _app_with_queue_config(default="redis", url="redis://localhost:6379/0")
    try:
        broker = QueueManager(app).broker  # constructs, does not connect
        assert isinstance(broker, ListQueueBroker)
    finally:
        set_application(None)


def test_amqp_driver_builds_an_aio_pika_broker() -> None:
    pytest.importorskip("taskiq_aio_pika")  # needs the [queue-amqp] extra
    from taskiq_aio_pika import AioPikaBroker

    from arvel.kernel import set_application

    app = _app_with_queue_config(default="amqp", url="amqp://guest:guest@localhost:5672//")
    try:
        broker = QueueManager(app).broker
        assert isinstance(broker, AioPikaBroker)
    finally:
        set_application(None)


def test_unknown_driver_raises_a_clear_error() -> None:
    from arvel.kernel import set_application

    app = _app_with_queue_config(default="kafka")
    try:
        with pytest.raises(ValueError, match="kafka"):
            _ = QueueManager(app).broker
    finally:
        set_application(None)
