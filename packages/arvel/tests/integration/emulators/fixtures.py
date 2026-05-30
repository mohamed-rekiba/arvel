"""Session-scoped Testcontainers fixtures for storage emulators.

Each fixture spins up the relevant Docker container, waits for it to be
ready, pre-creates the test bucket/container, and yields a typed endpoint
handle to the test. The container is torn down at the end of the session.

If Docker isn't available on the host, the fixture skips cleanly with an
actionable message instead of failing with a ``DockerException``.

Third-party libraries (testcontainers, boto3, azure-storage-blob,
google-cloud-storage) are loaded via :mod:`importlib` and cast to ``Any``,
matching the framework's existing optional-dependency convention (see
``arvel.storage.drivers.s3_``). That keeps pyright in strict mode without
requiring stub packages we don't ship.

Image pins live in :mod:`._images`. Bump versions there — the fixtures,
``Makefile``, and CI workflow all dereference the same constants.
"""

from __future__ import annotations

import importlib
import time
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest

from ._docker import docker_available
from ._images import (
    IMAGE_AZURITE,
    IMAGE_FAKE_GCS,
    IMAGE_MAILPIT,
    IMAGE_MOTO,
    IMAGE_MYSQL,
    IMAGE_POSTGRES,
    IMAGE_RABBITMQ,
    IMAGE_REDIS,
)

_AZURITE_ACCOUNT = "devstoreaccount1"
# Public well-known Azurite key from the official Microsoft documentation;
# accepted by every Azurite instance and not a secret in any meaningful sense.
_AZURITE_KEY = (
    "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="
)


@dataclass(frozen=True)
class S3Endpoint:
    """Connection details for the moto-server S3 emulator."""

    url: str
    region: str
    access_key: str
    secret_key: str
    bucket: str


@dataclass(frozen=True)
class AzuriteEndpoint:
    """Connection details for the Azurite Blob emulator."""

    connection_string: str
    account: str
    key: str
    container: str
    blob_endpoint: str


@dataclass(frozen=True)
class GcsEndpoint:
    """Connection details for the fake-gcs-server emulator."""

    api_endpoint: str
    project: str
    bucket: str


@dataclass(frozen=True)
class RedisEndpoint:
    """Connection details for the Redis-protocol emulator (run as Valkey)."""

    url: str
    host: str
    port: int


@dataclass(frozen=True)
class MailpitEndpoint:
    """Connection details for the Mailpit SMTP emulator."""

    smtp_host: str
    smtp_port: int
    api_url: str


@dataclass(frozen=True)
class PostgresEndpoint:
    """Connection details for the Postgres emulator."""

    host: str
    port: int
    user: str
    password: str
    database: str
    dsn_asyncpg: str
    dsn_psycopg: str


@dataclass(frozen=True)
class RabbitmqEndpoint:
    """Connection details for the RabbitMQ emulator (WI-018)."""

    url: str
    host: str
    port: int
    management_url: str


@dataclass(frozen=True)
class MysqlEndpoint:
    """Connection details for the MySQL-protocol emulator (run as MariaDB)."""

    host: str
    port: int
    user: str
    password: str
    database: str
    dsn_aiomysql: str
    dsn_pymysql: str


def _skip_if_no_docker() -> None:
    if not docker_available():
        pytest.skip(
            "Docker daemon unreachable; install Docker to run -m requires_emulator tests",
            allow_module_level=False,
        )


def _docker_container(image: str, *, ready_log: str, timeout: int = 60) -> Any:
    """Return an unstarted :class:`DockerContainer` for ``image``.

    Attaches a :class:`LogMessageWaitStrategy` so :meth:`start` returns only
    after the container has logged ``ready_log`` (or ``timeout`` seconds pass).
    Lazy-imported via :mod:`importlib` to keep pyright in strict mode without
    a testcontainers stub package.
    """
    tc_container: Any = importlib.import_module("testcontainers.core.container")
    tc_strategies: Any = importlib.import_module("testcontainers.core.wait_strategies")
    container = tc_container.DockerContainer(image)
    strategy = tc_strategies.LogMessageWaitStrategy(ready_log).with_startup_timeout(timeout)
    container.waiting_for(strategy)
    return container


@pytest.fixture(scope="session")
def s3_endpoint() -> Iterator[S3Endpoint]:
    """Boot a ``motoserver/moto`` container speaking the S3 wire protocol."""
    _skip_if_no_docker()

    bucket = "arvel-test-bucket"
    region = "us-east-1"
    access_key = "testing"
    secret_key = "testing"  # moto accepts any credential

    container = _docker_container(
        IMAGE_MOTO,
        ready_log="Running on http://",
    ).with_exposed_ports(5000)
    container.start()
    try:
        host: str = container.get_container_host_ip()
        port: str = container.get_exposed_port(5000)
        url = f"http://{host}:{port}"

        boto3: Any = importlib.import_module("boto3")
        client: Any = boto3.client(
            "s3",
            endpoint_url=url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        client.create_bucket(Bucket=bucket)

        yield S3Endpoint(
            url=url,
            region=region,
            access_key=access_key,
            secret_key=secret_key,
            bucket=bucket,
        )
    finally:
        container.stop()


@pytest.fixture(scope="session")
def azurite_endpoint() -> Iterator[AzuriteEndpoint]:
    """Boot an ``azurite`` container speaking the Azure Blob wire protocol."""
    _skip_if_no_docker()

    blob_container = "arvel-test-container"

    container = _docker_container(
        IMAGE_AZURITE,
        ready_log="Azurite Blob service successfully listens on",
    ).with_exposed_ports(10000)
    # --skipApiVersionCheck because the azure-storage-blob SDK pins newer
    # x-ms-version headers than each Azurite release tracks; emulator output
    # is the contract here, not the version handshake.
    container.with_command("azurite-blob --blobHost 0.0.0.0 --blobPort 10000 --skipApiVersionCheck")
    container.start()
    try:
        host: str = container.get_container_host_ip()
        port: str = container.get_exposed_port(10000)
        blob_endpoint = f"http://{host}:{port}/{_AZURITE_ACCOUNT}"
        connection_string = (
            f"DefaultEndpointsProtocol=http;"
            f"AccountName={_AZURITE_ACCOUNT};"
            f"AccountKey={_AZURITE_KEY};"
            f"BlobEndpoint={blob_endpoint};"
        )

        azure_blob: Any = importlib.import_module("azure.storage.blob")
        service: Any = azure_blob.BlobServiceClient.from_connection_string(connection_string)
        service.create_container(blob_container)

        yield AzuriteEndpoint(
            connection_string=connection_string,
            account=_AZURITE_ACCOUNT,
            key=_AZURITE_KEY,
            container=blob_container,
            blob_endpoint=blob_endpoint,
        )
    finally:
        container.stop()


@pytest.fixture(scope="session")
def gcs_endpoint() -> Iterator[GcsEndpoint]:
    """Boot an ``fsouza/fake-gcs-server`` container speaking the GCS wire protocol."""
    _skip_if_no_docker()

    bucket = "arvel-test-bucket"
    project = "arvel-test-project"

    container = _docker_container(
        IMAGE_FAKE_GCS,
        ready_log="server started at",
    ).with_exposed_ports(4443)
    # public-host is what the server inserts into media-link responses; tests
    # never follow those, but the server requires it to be set so URLs are
    # well-formed. -scheme http disables the default self-signed TLS cert.
    container.with_command("-scheme http -public-host localhost")
    container.start()
    try:
        host: str = container.get_container_host_ip()
        port: str = container.get_exposed_port(4443)
        api_endpoint = f"http://{host}:{port}"

        # Pre-create the bucket via the server's REST API rather than the GCS
        # client — keeps this fixture independent of google-cloud-storage's
        # quirks around anonymous credentials and project resolution.
        payload = f'{{"name": "{bucket}"}}'.encode()
        req = urllib.request.Request(  # noqa: S310 — fixed scheme, controlled URL
            f"{api_endpoint}/storage/v1/b?project={project}",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as response:  # noqa: S310
            assert response.status in {200, 409}, (
                f"fake-gcs bucket create failed: {response.status}"
            )

        yield GcsEndpoint(api_endpoint=api_endpoint, project=project, bucket=bucket)
    finally:
        container.stop()


@pytest.fixture(scope="session")
def redis_endpoint() -> Iterator[RedisEndpoint]:
    """Boot a Redis-protocol container and yield connection details.

    The container image is ``valkey/valkey`` — the OSS Redis fork — pinned
    in :mod:`._images` as :data:`IMAGE_REDIS`. Valkey speaks the RESP wire
    protocol unchanged, so the ``redis`` Python client, ``taskiq-redis``
    broker, and Arvel's Redis-backed drivers (cache, session, queue,
    broadcasting, reverb) all connect without modification. Used by the
    integration tests to exercise the real wire protocol instead of
    fakeredis.
    """
    _skip_if_no_docker()

    container = _docker_container(
        IMAGE_REDIS,
        ready_log="Ready to accept connections",
    ).with_exposed_ports(6379)
    container.start()
    try:
        host: str = container.get_container_host_ip()
        port: int = int(container.get_exposed_port(6379))
        yield RedisEndpoint(url=f"redis://{host}:{port}/0", host=host, port=port)
    finally:
        container.stop()


@pytest.fixture(scope="session")
def mailpit_endpoint() -> Iterator[MailpitEndpoint]:
    """Boot an ``axllent/mailpit`` container exposing SMTP + a JSON inbox API.

    Tests deliver via the SMTP listener on port 1025, then poll the HTTP API
    on port 8025 (``/api/v1/messages``) to assert the message arrived. This
    avoids the brittleness of parsing maildir files on the host.
    """
    _skip_if_no_docker()

    container = _docker_container(
        IMAGE_MAILPIT,
        # Mailpit logs both an SMTP-ready line and an HTTP-ready line; the
        # HTTP one comes last and means both surfaces are live.
        ready_log="accessible via",
    )
    container.with_exposed_ports(1025, 8025)
    container.start()
    try:
        host: str = container.get_container_host_ip()
        smtp_port: int = int(container.get_exposed_port(1025))
        api_port: int = int(container.get_exposed_port(8025))
        yield MailpitEndpoint(
            smtp_host=host,
            smtp_port=smtp_port,
            api_url=f"http://{host}:{api_port}",
        )
    finally:
        container.stop()


@pytest.fixture(scope="session")
def postgres_endpoint() -> Iterator[PostgresEndpoint]:
    """Boot a ``postgres:18-alpine`` container and yield asyncpg + psycopg DSNs."""
    _skip_if_no_docker()

    user = "arvel"
    password = "arvel"  # well-known test password; emulator is unreachable from outside
    database = "arvel_test"

    container = _docker_container(
        IMAGE_POSTGRES,
        # Postgres prints "database system is ready to accept connections"
        # twice on startup: once after initial bootstrap, then again after
        # listening on TCP. We wait for the second to guarantee the socket
        # is up, but a regex on the unique listen-port suffix is more robust
        # than counting occurrences.
        ready_log=r"database system is ready to accept connections",
        timeout=120,
    )
    container.with_env("POSTGRES_USER", user)
    container.with_env("POSTGRES_PASSWORD", password)
    container.with_env("POSTGRES_DB", database)
    container.with_exposed_ports(5432)
    container.start()
    try:
        host: str = container.get_container_host_ip()
        port: int = int(container.get_exposed_port(5432))
        dsn_asyncpg = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"
        dsn_psycopg = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{database}"
        _wait_for_postgres(host, port, user, password, database)
        yield PostgresEndpoint(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            dsn_asyncpg=dsn_asyncpg,
            dsn_psycopg=dsn_psycopg,
        )
    finally:
        container.stop()


@pytest.fixture(scope="session")
def mysql_endpoint() -> Iterator[MysqlEndpoint]:
    """Boot a MySQL-protocol container and yield aiomysql + pymysql DSNs.

    The container image is ``mariadb`` — the OSS MySQL fork — pinned in
    :mod:`._images` as :data:`IMAGE_MYSQL`. MariaDB speaks the MySQL wire
    protocol, so ``aiomysql`` / ``pymysql`` connect unchanged and the
    DSN scheme stays ``mysql+<driver>://`` (the SQLAlchemy dialect for
    MySQL-protocol servers). Env vars use the ``MARIADB_*`` names the
    image expects natively.
    """
    _skip_if_no_docker()

    user = "arvel"
    password = "arvel"  # well-known test password; emulator is unreachable from outside
    database = "arvel_test"
    root_password = "arvel-root"

    container = _docker_container(
        IMAGE_MYSQL,
        # MariaDB logs "mariadbd: ready for connections" once the TCP
        # listener is up; the polling probe below is the real readiness
        # gate (it catches the gap before grants are applied).
        ready_log=r"ready for connections",
        timeout=180,
    )
    container.with_env("MARIADB_ROOT_PASSWORD", root_password)
    container.with_env("MARIADB_USER", user)
    container.with_env("MARIADB_PASSWORD", password)
    container.with_env("MARIADB_DATABASE", database)
    container.with_exposed_ports(3306)
    container.start()
    try:
        host: str = container.get_container_host_ip()
        port: int = int(container.get_exposed_port(3306))
        dsn_aiomysql = f"mysql+aiomysql://{user}:{password}@{host}:{port}/{database}"
        dsn_pymysql = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
        _wait_for_mysql(host, port, user, password, database)
        yield MysqlEndpoint(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            dsn_aiomysql=dsn_aiomysql,
            dsn_pymysql=dsn_pymysql,
        )
    finally:
        container.stop()


@pytest.fixture(scope="session")
def rabbitmq_endpoint() -> Iterator[RabbitmqEndpoint]:
    """Boot a RabbitMQ container speaking AMQP, yield connection details (WI-018).

    The image is ``rabbitmq:<X>-management-alpine`` pinned in :mod:`._images`
    as :data:`IMAGE_RABBITMQ`. Image variant ``management-alpine`` adds the
    HTTP management plugin (port 15672) so debugging tests can poke the
    queue browser without rebuilding the image.

    Readiness is gated by the ``Server startup complete`` log line plus a
    poll on the management API to close the gap between TCP-listening and
    the AMQP protocol being available for connections.
    """
    _skip_if_no_docker()

    container = _docker_container(
        IMAGE_RABBITMQ,
        ready_log=r"Server startup complete",
        timeout=180,
    )
    container.with_exposed_ports(5672, 15672)
    container.start()
    try:
        host: str = container.get_container_host_ip()
        amqp_port: int = int(container.get_exposed_port(5672))
        mgmt_port: int = int(container.get_exposed_port(15672))
        url = f"amqp://guest:guest@{host}:{amqp_port}/"
        mgmt_url = f"http://guest:guest@{host}:{mgmt_port}"
        _wait_for_rabbitmq(host, mgmt_port)
        yield RabbitmqEndpoint(url=url, host=host, port=amqp_port, management_url=mgmt_url)
    finally:
        container.stop()


def _wait_for_postgres(
    host: str, port: int, user: str, password: str, database: str, *, timeout: float = 30.0
) -> None:
    """Poll Postgres with a real psycopg connect() until it accepts queries.

    The container log strategy catches the listener coming up, but Postgres
    transiently refuses connections during init-script execution. Polling
    a trivial ``SELECT 1`` here closes that race.
    """
    psycopg: Any = importlib.import_module("psycopg")
    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            conn: Any = psycopg.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                dbname=database,
                connect_timeout=2,
            )
        except Exception as exc:
            last_exc = exc
            time.sleep(0.5)
            continue
        try:
            conn.execute("SELECT 1")
        finally:
            conn.close()
        return
    raise RuntimeError(f"Postgres at {host}:{port} did not become ready in {timeout}s: {last_exc}")


def _wait_for_mysql(
    host: str, port: int, user: str, password: str, database: str, *, timeout: float = 60.0
) -> None:
    """Poll the MySQL-protocol server with a real pymysql connect() until it accepts queries."""
    pymysql: Any = importlib.import_module("pymysql")
    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            conn: Any = pymysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                connect_timeout=2,
            )
        except Exception as exc:
            last_exc = exc
            time.sleep(1.0)
            continue
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        finally:
            conn.close()
        return
    raise RuntimeError(f"MySQL at {host}:{port} did not become ready in {timeout}s: {last_exc}")


def _wait_for_rabbitmq(host: str, mgmt_port: int, *, timeout: float = 60.0) -> None:
    """Poll the RabbitMQ management API until it accepts requests (WI-018).

    The log strategy catches Erlang startup but the AMQP listener and the
    management plugin can lag by a few hundred ms. Polling the management
    health endpoint here closes the race before tests start dialling AMQP.
    """
    deadline = time.monotonic() + timeout
    url = f"http://{host}:{mgmt_port}/api/overview"
    # Public well-known emulator credentials; container is local-only.
    auth = "Basic " + __import__("base64").b64encode(b"guest:guest").decode()
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(  # noqa: S310 — fixed scheme, controlled URL
                url, headers={"Authorization": auth}
            )
            with urllib.request.urlopen(req, timeout=2) as response:  # noqa: S310
                if 200 <= response.status < 300:
                    return
        except Exception as exc:
            last_exc = exc
        time.sleep(0.5)
    raise RuntimeError(
        f"RabbitMQ management API at {host}:{mgmt_port} did not become ready in {timeout}s: "
        f"{last_exc}"
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
    "azurite_endpoint",
    "gcs_endpoint",
    "mailpit_endpoint",
    "mysql_endpoint",
    "postgres_endpoint",
    "rabbitmq_endpoint",
    "redis_endpoint",
    "s3_endpoint",
]
