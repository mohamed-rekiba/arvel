"""Queue configuration — RabbitMQ broker backs every background job.

The framework reads ``QUEUE_CONNECTION`` (``QueueConfig.connection``).
This module mirrors the Laravel-shaped connection inventory.
"""

from __future__ import annotations

from arvel.support.env import env

default: str = env("QUEUE_CONNECTION", "sync")

connections: dict[str, dict[str, object]] = {
    "rabbitmq": {
        "driver": "amqp",
        "url": env("AMQP_URL", "amqp://guest:guest@localhost:5672/"),
        "queue": env("QUEUE_NAME", "default"),
    },
    "sync": {
        "driver": "sync",
    },
}
