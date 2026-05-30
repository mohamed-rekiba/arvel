"""Testcontainers-backed emulator fixtures for integration tests.

The fixtures here boot real backend services on demand so Arvel's drivers
can be exercised against the actual wire protocol instead of in-process
mocks. Eight emulators are provided: S3 (moto-server), Azure Blob
(Azurite), GCS (fake-gcs-server), Redis (Valkey OSS fork), SMTP
(Mailpit), Postgres, MySQL (MariaDB OSS fork), and RabbitMQ.

All fixtures are session-scoped and ``@pytest.mark.requires_emulator``-gated,
so they only start a container when a test that needs one is collected.
Image pins are centralized in :mod:`._images` — bump versions there.
"""

from __future__ import annotations

from .fixtures import (
    AzuriteEndpoint,
    GcsEndpoint,
    MailpitEndpoint,
    MysqlEndpoint,
    PostgresEndpoint,
    RabbitmqEndpoint,
    RedisEndpoint,
    S3Endpoint,
)

__all__ = [
    "AzuriteEndpoint",
    "GcsEndpoint",
    "MailpitEndpoint",
    "MysqlEndpoint",
    "PostgresEndpoint",
    "RabbitmqEndpoint",
    "RedisEndpoint",
    "S3Endpoint",
]
