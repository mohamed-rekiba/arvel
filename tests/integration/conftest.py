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
    """Build a real ``Application`` and make it the global app — managers' typed ``Settings`` read
    config off the global app, so a plain dict fake won't do. Resets on teardown."""
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
    """A throwaway Postgres with the pgvector server extension preinstalled — the stock image
    lacks the control file `CREATE EXTENSION vector` needs."""
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
    """A throwaway RustFS (S3-compatible store); yields endpoint + credentials for the s3 disk,
    waiting until the server actually accepts S3 calls."""
    import time

    import s3fs
    from testcontainers.core.generic import DockerContainer
    from testcontainers.core.wait_strategies import LogMessageWaitStrategy

    container = (
        DockerContainer("rustfs/rustfs:latest")
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
    """A throwaway Azurite (Azure blob emulator); yields the connection string."""
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
    """A throwaway MySQL-family server, yielded as an asyncmy URL. Defaults to MariaDB (same
    driver/dialect as MySQL); override ``ARVEL_MYSQL_IMAGE`` to test against e.g. ``mysql:8.4``."""
    import os

    pytest.importorskip("testcontainers.mysql")
    from testcontainers.mysql import MySqlContainer

    image = os.environ.get("ARVEL_MYSQL_IMAGE", "mariadb:11.8.6")
    with MySqlContainer(image, dialect="asyncmy") as mysql:
        yield mysql.get_connection_url()


@pytest.fixture(scope="session")
def meilisearch_url() -> Iterator[dict[str, str]]:
    """A throwaway Meilisearch server; yields ``{"url": ..., "key": ...}``. Probed with the real
    client's ``health()`` until it answers — Meilisearch's startup log format isn't stable enough
    across versions to key a ``LogMessageWaitStrategy`` off, unlike the other fixtures here."""
    import time

    import meilisearch
    from testcontainers.core.generic import DockerContainer

    master_key = "arvel-test-master-key"  # fixed test-only key, not a real secret
    container = (
        DockerContainer("getmeili/meilisearch:v1.11")
        .with_exposed_ports(7700)
        .with_env("MEILI_MASTER_KEY", master_key)
        .with_env("MEILI_NO_ANALYTICS", "true")
    )
    with container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(7700)
        url = f"http://{host}:{port}"
        client = meilisearch.Client(url, master_key)
        for _ in range(60):
            try:
                client.health()
                break
            except Exception:
                time.sleep(0.5)
        yield {"url": url, "key": master_key}


@pytest.fixture(scope="session")
def rabbitmq_url() -> Iterator[str]:
    """A throwaway RabbitMQ (any AMQP broker works); yields an ``amqp://`` URL."""
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
    """A throwaway OpenTelemetry Collector receiving OTLP/HTTP on 4318 and printing signals via the
    debug exporter; yields the container so a test can read its logs."""
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
