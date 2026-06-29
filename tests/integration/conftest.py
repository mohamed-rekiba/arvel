"""Integration tier — real services via testcontainers. Skips cleanly without Docker."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

pytest.importorskip("testcontainers.postgres")


def _docker_available() -> bool:
    try:
        import docker
    except ImportError:
        return False
    try:
        docker.from_env().ping()
    except Exception:
        return False
    return True


pytestmark = pytest.mark.skipif(not _docker_available(), reason="Docker not available")


@pytest.fixture
def configure_app() -> Iterator[Any]:
    """Build a real ``Application`` with the given config sections and make it the global app, so the
    managers' typed ``Settings`` (which read the global ``config()``) see them. Resets on teardown.

    Usage: ``app = configure_app(cache={"default": "redis", "url": url})``. A plain dict fake won't do
    — ``Settings`` read ``config(section)`` off the **global** app's config repository (DR-0016)."""
    from arvel.kernel import Application, set_application

    def _make(**sections: Any) -> Any:
        app = Application()
        repo = app.make("config")
        for key, value in sections.items():
            repo.set(key, value)
        set_application(app)
        return app

    try:
        yield _make
    finally:
        from arvel.kernel import set_application

        set_application(None)


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """A throwaway Postgres, yielded as an asyncpg URL; torn down after the session."""
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def pgvector_url() -> Iterator[str]:
    """A throwaway Postgres with the pgvector **server extension** preinstalled (the stock
    postgres image lacks it — `CREATE EXTENSION vector` needs the control file on the server)."""
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("pgvector/pgvector:pg16", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    """A throwaway Redis, yielded as a ``redis://`` URL; torn down after the session."""
    pytest.importorskip("testcontainers.redis")
    from testcontainers.redis import RedisContainer

    with RedisContainer("redis:7-alpine") as rc:
        yield f"redis://{rc.get_container_host_ip()}:{rc.get_exposed_port(6379)}/0"


@pytest.fixture(scope="session")
def rustfs_s3() -> Iterator[dict[str, str]]:
    """A throwaway RustFS (the S3-compatible store named by doc 20); yields the endpoint +
    credentials for the s3 disk. Waits for the server to actually accept S3 calls."""
    import time

    import s3fs
    from testcontainers.core.generic import DockerContainer
    from testcontainers.core.wait_strategies import LogMessageWaitStrategy

    container = (
        DockerContainer("rustfs/rustfs:latest")  # default creds
        .with_exposed_ports(9000)
        .waiting_for(LogMessageWaitStrategy("Starting:").with_startup_timeout(60))
    )
    with container:
        endpoint = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(9000)}"
        creds = {"endpoint_url": endpoint, "key": "rustfsadmin", "secret": "rustfsadmin"}
        # the entrypoint logs "Starting:" before the API binds — probe until it answers
        probe = s3fs.S3FileSystem(
            key=creds["key"], secret=creds["secret"], client_kwargs={"endpoint_url": endpoint}
        )
        for _ in range(60):
            try:
                probe.ls("")
                break
            except Exception:
                time.sleep(0.5)
        yield creds


@pytest.fixture(scope="session")
def azurite_conn() -> Iterator[str]:
    """A throwaway Azurite (Azure blob emulator, named by doc 20); yields the connection string."""
    pytest.importorskip("adlfs")
    from testcontainers.core.generic import DockerContainer
    from testcontainers.core.wait_strategies import LogMessageWaitStrategy

    container = (
        DockerContainer("mcr.microsoft.com/azure-storage/azurite:latest")
        .with_exposed_ports(10000)
        # --skipApiVersionCheck: accept the newer azure-sdk API version the client sends
        .with_command("azurite-blob --blobHost 0.0.0.0 --blobPort 10000 --skipApiVersionCheck")
        .waiting_for(
            LogMessageWaitStrategy("Blob service successfully listens").with_startup_timeout(60)
        )
    )
    with container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(10000)
        # the well-known Azurite dev account + key (public, fixed) — not a real secret
        key = "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="
        yield (
            "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;"
            f"AccountKey={key};BlobEndpoint=http://{host}:{port}/devstoreaccount1;"
        )


@pytest.fixture(scope="session")
def mysql_url() -> Iterator[str]:
    """A throwaway MySQL-family server, yielded as an asyncmy URL; torn down after the session.

    Defaults to MariaDB (MySQL wire-compatible — same ``asyncmy`` driver + ``mysql`` SQLAlchemy
    dialect, so it exercises the identical MySQL code path). Override ``ARVEL_MYSQL_IMAGE`` to test
    against ``mysql:8.4`` etc. where that image is available."""
    import os

    pytest.importorskip("testcontainers.mysql")
    from testcontainers.mysql import MySqlContainer

    image = os.environ.get("ARVEL_MYSQL_IMAGE", "mariadb:11.8.6")
    with MySqlContainer(image, dialect="asyncmy") as mysql:
        yield mysql.get_connection_url()


@pytest.fixture(scope="session")
def rabbitmq_url() -> Iterator[str]:
    """A throwaway RabbitMQ (any AMQP broker — LavinMQ works the same); yields an ``amqp://`` URL.
    Uses the generic container so no extra ``pika`` dependency is needed for readiness."""
    from testcontainers.core.generic import DockerContainer
    from testcontainers.core.wait_strategies import LogMessageWaitStrategy

    container = (
        DockerContainer("rabbitmq:4.3.0-management-alpine")
        .with_exposed_ports(5672)
        .waiting_for(LogMessageWaitStrategy("Server startup complete").with_startup_timeout(90))
    )
    with container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(5672)
        yield f"amqp://guest:guest@{host}:{port}/"


@pytest.fixture(scope="session")
def otel_collector() -> Iterator[Any]:
    """A throwaway OpenTelemetry Collector receiving OTLP/HTTP on 4318 and printing received signals
    via the debug exporter; yields the container so a test can read its logs. Backend-agnostic — the
    same OTLP push works against Grafana/Tempo/any OTLP endpoint."""
    from pathlib import Path

    from testcontainers.core.generic import DockerContainer
    from testcontainers.core.wait_strategies import LogMessageWaitStrategy

    config = str(Path(__file__).parent / "otelcol-config.yaml")
    container = (
        DockerContainer("otel/opentelemetry-collector-contrib:0.155.0")
        .with_exposed_ports(4318)
        .with_volume_mapping(config, "/etc/otelcol-contrib/config.yaml")
        .waiting_for(LogMessageWaitStrategy("Everything is ready").with_startup_timeout(60))
    )
    with container:
        yield container
