"""Testcontainers harness for the e-commerce kit.

Boots Postgres 18, Redis 7, RabbitMQ 3.13, MinIO, and Mailpit once per
session. Per-test isolation via the template-DB pattern (same as arvel-starter).

Container images are pinned — update via web search before each WI bump.
"""

from __future__ import annotations

import importlib
import os
import sys
import time
import urllib.request
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

# Every fixture below cleans up via try/finally: container.stop(), so the Ryuk
# reaper is redundant. Disabling it also drops the implicit testcontainers/ryuk
# pull from Docker Hub — that pull isn't in our pinned image set and stalls on
# CI runners that Docker Hub rate-limits, which looks like a hang at "bringing up
# nodes...". setdefault so a host override wins. Must run before
# testcontainers.core.config is imported (it reads this once); conftest loads at
# session start, ahead of the lazy import in _docker_container.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

# pytest puts this conftest's directory on sys.path before executing it, so the
# sibling _images module (single source of truth for image pins) imports here.
from _images import (
    IMAGE_MAILPIT,
    IMAGE_MOTO,
    IMAGE_POSTGRES,
    IMAGE_RABBITMQ,
    IMAGE_REDIS,
)

_BACKEND_ROOT = str(Path(__file__).resolve().parents[1])
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

_POSTGRES_USER = "arvel"
_POSTGRES_PASSWORD = "arvel"  # well-known test credential; container is local-only
_POSTGRES_BASE_DB = "arvel_ecommerce_test"
_TEMPLATE_DB_NAME = "arvel_ecommerce_template"
_SEEDED_TEMPLATE_DB_NAME = "arvel_ecommerce_seeded"


@dataclass(frozen=True)
class PostgresEndpoint:
    host: str
    port: int
    user: str
    password: str
    base_database: str
    dsn_asyncpg_admin: str
    dsn_psycopg_admin: str

    def dsn_asyncpg(self, dbname: str) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{dbname}"

    def dsn_psycopg(self, dbname: str) -> str:
        return f"postgresql+psycopg://{self.user}:{self.password}@{self.host}:{self.port}/{dbname}"


@dataclass(frozen=True)
class RedisEndpoint:
    host: str
    port: int

    @property
    def url(self) -> str:
        return f"redis://{self.host}:{self.port}/0"


@dataclass(frozen=True)
class RabbitmqEndpoint:
    host: str
    amqp_port: int
    management_port: int

    @property
    def amqp_url(self) -> str:
        return f"amqp://guest:guest@{self.host}:{self.amqp_port}/"

    @property
    def management_url(self) -> str:
        return f"http://guest:guest@{self.host}:{self.management_port}"


@dataclass(frozen=True)
class S3Endpoint:
    endpoint_url: str
    region: str
    access_key: str
    secret_key: str
    bucket: str


@dataclass(frozen=True)
class MailpitEndpoint:
    smtp_host: str
    smtp_port: int
    api_url: str


def _docker_available() -> bool:
    try:
        docker_mod: Any = importlib.import_module("docker")
        client: Any = docker_mod.from_env()
        client.ping()
    except Exception:
        return False
    return True


def _skip_if_no_docker() -> None:
    if not _docker_available():
        pytest.skip(
            "Docker daemon unreachable; install Docker to run the testcontainers harness",
            allow_module_level=False,
        )


def _docker_container(image: str, *, ready_log: str, timeout: int = 120) -> Any:
    tc_container: Any = importlib.import_module("testcontainers.core.container")
    tc_strategies: Any = importlib.import_module("testcontainers.core.wait_strategies")
    container = tc_container.DockerContainer(image)
    strategy = tc_strategies.LogMessageWaitStrategy(ready_log).with_startup_timeout(timeout)
    container.waiting_for(strategy)
    return container


# Containers are session-scoped, so each xdist worker boots its own stack on the
# first emulator test it runs. Across workers they hit *different* containers, so
# the shared default DB/vhost/bucket is safe without per-test isolation.
#
# The catalog seed (14 image downloads + conversion generation) is the expensive
# part, ~12s. It used to run per test (about 93 times). Now it runs once per worker
# into the seeded template DB; every test's `fresh_db` is a CREATE DATABASE ...
# TEMPLATE clone of it (~0.03s). That's the whole speedup: seed once, clone cheaply.


@pytest.fixture(scope="session")
def postgres_endpoint() -> Iterator[PostgresEndpoint]:
    _skip_if_no_docker()
    container = _docker_container(
        IMAGE_POSTGRES,
        ready_log=r"database system is ready to accept connections",
    )
    container.with_env("POSTGRES_USER", _POSTGRES_USER)
    container.with_env("POSTGRES_PASSWORD", _POSTGRES_PASSWORD)
    container.with_env("POSTGRES_DB", _POSTGRES_BASE_DB)
    container.with_exposed_ports(5432)
    container.start()
    try:
        host: str = container.get_container_host_ip()
        port: int = int(container.get_exposed_port(5432))
        endpoint = PostgresEndpoint(
            host=host,
            port=port,
            user=_POSTGRES_USER,
            password=_POSTGRES_PASSWORD,
            base_database=_POSTGRES_BASE_DB,
            dsn_asyncpg_admin=f"postgresql+asyncpg://{_POSTGRES_USER}:{_POSTGRES_PASSWORD}@{host}:{port}/postgres",
            dsn_psycopg_admin=f"postgresql+psycopg://{_POSTGRES_USER}:{_POSTGRES_PASSWORD}@{host}:{port}/postgres",
        )
        _wait_for_postgres(endpoint)
        yield endpoint
    finally:
        container.stop()


@pytest.fixture(scope="session")
def template_db(postgres_endpoint: PostgresEndpoint) -> str:
    """Create the template database once per session with all e-commerce migrations applied."""
    _create_database(postgres_endpoint, _TEMPLATE_DB_NAME)
    template_dsn = postgres_endpoint.dsn_asyncpg(_TEMPLATE_DB_NAME)

    import asyncio
    from pathlib import Path

    from arvel.database.migrator import Migrator
    from sqlalchemy.ext.asyncio import create_async_engine

    backend_root = Path(__file__).resolve().parent.parent
    migrations_path = backend_root / "database" / "migrations"

    engine = create_async_engine(template_dsn)
    migrator = Migrator(engine=engine, migrations_path=migrations_path)

    async def _apply() -> None:
        await migrator.ensure_table()
        await migrator.upgrade()
        await engine.dispose()

    asyncio.run(_apply())
    return template_dsn


@pytest.fixture(scope="session")
def seeded_template_db(
    postgres_endpoint: PostgresEndpoint,
    template_db: str,
    redis_endpoint: RedisEndpoint,
    rabbitmq_endpoint: RabbitmqEndpoint,
    s3_endpoint: S3Endpoint,
    mailpit_endpoint: MailpitEndpoint,
) -> str:
    """Build the catalog-seeded template once per worker; fresh_db clones it.

    Boots the app against a throwaway DB, runs the catalog seed (the costly bit),
    then leaves that DB untouched so it can serve as a CREATE DATABASE template.
    Images land in the shared session S3, which every clone references.
    """
    import asyncio

    _create_database(postgres_endpoint, _SEEDED_TEMPLATE_DB_NAME, template=_TEMPLATE_DB_NAME)

    env = {
        "DB_URL": postgres_endpoint.dsn_asyncpg(_SEEDED_TEMPLATE_DB_NAME),
        "CACHE_URL": redis_endpoint.url,
        "AMQP_URL": rabbitmq_endpoint.amqp_url,
        "STORAGE_S3_ENDPOINT": s3_endpoint.endpoint_url,
        "STORAGE_S3_KEY": s3_endpoint.access_key,
        "STORAGE_S3_SECRET": s3_endpoint.secret_key,
        "STORAGE_S3_BUCKET": s3_endpoint.bucket,
        "MAIL_HOST": mailpit_endpoint.smtp_host,
        "MAIL_PORT": str(mailpit_endpoint.smtp_port),
        "APP_ENV": "local",
        "APP_KEY": "seeded-template-key-must-be-32-bytes-or-more!",
    }
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)

    async def _seed() -> None:
        from app.bootstrap import create_app

        app = await create_app()
        try:
            await app.seed("catalog")
        finally:
            await app.shutdown()

    try:
        asyncio.run(_seed())
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    return _SEEDED_TEMPLATE_DB_NAME


@pytest.fixture
async def fresh_db(
    postgres_endpoint: PostgresEndpoint, seeded_template_db: str
) -> AsyncIterator[str]:
    dbname = f"test_{uuid.uuid4().hex[:8]}"
    _create_database(postgres_endpoint, dbname, template=seeded_template_db)
    try:
        yield postgres_endpoint.dsn_asyncpg(dbname)
    finally:
        _drop_database(postgres_endpoint, dbname)


@pytest.fixture(scope="session")
def redis_endpoint() -> Iterator[RedisEndpoint]:
    _skip_if_no_docker()
    container = _docker_container(IMAGE_REDIS, ready_log=r"Ready to accept connections")
    container.with_exposed_ports(6379)
    container.start()
    try:
        host: str = container.get_container_host_ip()
        port: int = int(container.get_exposed_port(6379))
        yield RedisEndpoint(host=host, port=port)
    finally:
        container.stop()


@pytest.fixture(scope="session")
def rabbitmq_endpoint() -> Iterator[RabbitmqEndpoint]:
    _skip_if_no_docker()
    container = _docker_container(IMAGE_RABBITMQ, ready_log=r"Server startup complete", timeout=180)
    container.with_exposed_ports(5672, 15672)
    container.start()
    try:
        host: str = container.get_container_host_ip()
        amqp_port: int = int(container.get_exposed_port(5672))
        mgmt_port: int = int(container.get_exposed_port(15672))
        endpoint = RabbitmqEndpoint(host=host, amqp_port=amqp_port, management_port=mgmt_port)
        _wait_for_rabbitmq(endpoint)
        yield endpoint
    finally:
        container.stop()


@pytest.fixture(scope="session")
def s3_endpoint() -> Iterator[S3Endpoint]:
    """Boot a motoserver/moto container speaking the S3 wire protocol."""
    _skip_if_no_docker()
    bucket = "arvel-ecommerce"
    region = "us-east-1"
    access_key = "testing"
    secret_key = "testing"  # moto accepts any credential
    container = _docker_container(IMAGE_MOTO, ready_log=r"Running on http://")
    container.with_exposed_ports(5000)
    container.start()
    try:
        host: str = container.get_container_host_ip()
        port: int = int(container.get_exposed_port(5000))
        endpoint_url = f"http://{host}:{port}"
        boto3: Any = importlib.import_module("boto3")
        client: Any = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        client.create_bucket(Bucket=bucket)
        yield S3Endpoint(
            endpoint_url=endpoint_url,
            region=region,
            access_key=access_key,
            secret_key=secret_key,
            bucket=bucket,
        )
    finally:
        container.stop()


@pytest.fixture(scope="session")
def mailpit_endpoint() -> Iterator[MailpitEndpoint]:
    _skip_if_no_docker()
    container = _docker_container(IMAGE_MAILPIT, ready_log=r"accessible via")
    container.with_exposed_ports(1025, 8025)
    container.start()
    try:
        host: str = container.get_container_host_ip()
        smtp_port: int = int(container.get_exposed_port(1025))
        api_port: int = int(container.get_exposed_port(8025))
        yield MailpitEndpoint(
            smtp_host=host, smtp_port=smtp_port, api_url=f"http://{host}:{api_port}"
        )
    finally:
        container.stop()


def _wait_for_postgres(endpoint: PostgresEndpoint, *, timeout: float = 30.0) -> None:
    psycopg: Any = importlib.import_module("psycopg")
    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            conn: Any = psycopg.connect(
                host=endpoint.host,
                port=endpoint.port,
                user=endpoint.user,
                password=endpoint.password,
                dbname="postgres",
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
    msg = f"Postgres at {endpoint.host}:{endpoint.port} not ready in {timeout}s: {last_exc}"
    raise RuntimeError(msg)


def _create_database(
    endpoint: PostgresEndpoint, dbname: str, *, template: str | None = None
) -> None:
    psycopg: Any = importlib.import_module("psycopg")
    conn: Any = psycopg.connect(
        host=endpoint.host,
        port=endpoint.port,
        user=endpoint.user,
        password=endpoint.password,
        dbname="postgres",
        autocommit=True,
    )
    try:
        conn.execute(f'DROP DATABASE IF EXISTS "{dbname}"')
        if template is None:
            conn.execute(f'CREATE DATABASE "{dbname}"')
        else:
            conn.execute(f'CREATE DATABASE "{dbname}" TEMPLATE "{template}"')
    finally:
        conn.close()


def _drop_database(endpoint: PostgresEndpoint, dbname: str) -> None:
    psycopg: Any = importlib.import_module("psycopg")
    conn: Any = psycopg.connect(
        host=endpoint.host,
        port=endpoint.port,
        user=endpoint.user,
        password=endpoint.password,
        dbname="postgres",
        autocommit=True,
    )
    try:
        conn.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
    finally:
        conn.close()


def _wait_for_rabbitmq(endpoint: RabbitmqEndpoint, *, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    url = f"http://{endpoint.host}:{endpoint.management_port}/api/overview"
    auth = "Basic " + __import__("base64").b64encode(b"guest:guest").decode()
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(  # noqa: S310 # nosec B310
                url, headers={"Authorization": auth}
            )
            with urllib.request.urlopen(req, timeout=2) as response:  # noqa: S310 # nosec B310
                if 200 <= response.status < 300:
                    return
        except Exception as exc:
            last_exc = exc
        time.sleep(0.5)
    msg = (
        f"RabbitMQ management API at {endpoint.host}:{endpoint.management_port} "
        f"not ready in {timeout}s: {last_exc}"
    )
    raise RuntimeError(msg)


__all__ = [
    "MailpitEndpoint",
    "PostgresEndpoint",
    "RabbitmqEndpoint",
    "RedisEndpoint",
    "S3Endpoint",
    "fresh_db",
    "mailpit_endpoint",
    "postgres_endpoint",
    "rabbitmq_endpoint",
    "redis_endpoint",
    "s3_endpoint",
    "template_db",
]
