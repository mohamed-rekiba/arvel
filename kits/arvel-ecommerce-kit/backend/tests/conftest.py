"""Testcontainers harness for the e-commerce kit.

Boots Postgres 18, Redis 7, RabbitMQ 3.13, MinIO, and Mailpit *once for the whole
test run* — even under ``pytest -n auto``. The first xdist worker to need a
container boots it; every other worker connects to the same one over a filelock +
JSON state file in the shared tmp dir. The booting worker owns teardown and only
stops the container once every worker has released it (refcounted, timeout-bounded
so a crashed worker can't deadlock shutdown).

One shared stack instead of one-per-worker is what makes ``--dist load`` pay off:
on a small CI runner, N worker stacks (Nx5 containers) just thrash the CPU/disk
and parallelism evaporates. With a single stack, workers isolate per-worker —
Postgres via the template-DB pattern (unique DB per test), Redis via a per-worker
db index, RabbitMQ via a per-worker vhost, S3 via a per-worker bucket — so they
run concurrently without colliding. Run under ``--dist load``.

Container images are pinned — update via web search before each WI bump.
"""

from __future__ import annotations

import base64
import contextlib
import importlib
import json
import os
import sys
import time
import urllib.request
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from filelock import FileLock

# Every fixture below cleans up explicitly, so the Ryuk reaper is redundant.
# Disabling it also drops the implicit testcontainers/ryuk pull from Docker Hub —
# that pull isn't in our pinned image set and stalls on CI runners that Docker Hub
# rate-limits, which looks like a hang at "bringing up nodes...". setdefault so a
# host override wins. Must run before testcontainers.core.config is imported (it
# reads this once); conftest loads at session start, ahead of the lazy import in
# _docker_container.
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

# How long the container's owner waits for every other worker to release before it
# stops the container anyway. Bounds shutdown if a worker dies without cleaning up.
_OWNER_TEARDOWN_TIMEOUT = 90.0


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
    db: int = 0

    @property
    def url(self) -> str:
        return f"redis://{self.host}:{self.port}/{self.db}"


@dataclass(frozen=True)
class RabbitmqEndpoint:
    host: str
    amqp_port: int
    management_port: int
    vhost: str = "/"

    @property
    def amqp_url(self) -> str:
        return f"amqp://guest:guest@{self.host}:{self.amqp_port}/{self.vhost}"

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


# ─── xdist coordination ──────────────────────────────────────────────────────


def _worker_tag() -> str:
    """xdist worker id ("gw0", "gw1", ...) or "main" outside xdist."""
    return os.environ.get("PYTEST_XDIST_WORKER") or "main"


def _worker_db_index() -> int:
    """Redis db index for this worker (0-15). Caps at 16 workers per Redis instance."""
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if not worker:
        return 0
    digits = "".join(c for c in worker if c.isdigit())
    return (int(digits) if digits else 0) % 16


def _shared_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Tmp dir visible to every worker. Workers nest under the master's basetemp."""
    base = tmp_path_factory.getbasetemp()
    return base.parent if os.environ.get("PYTEST_XDIST_WORKER") else base


@contextmanager
def _shared_container(
    shared_dir: Path,
    key: str,
    boot: Callable[[], tuple[Any, dict[str, Any]]],
) -> Iterator[dict[str, Any]]:
    """Boot ``key``'s container once across all workers; share its connection info.

    ``boot`` starts the container, waits for readiness, and returns
    ``(container_handle, connection_dict)``. The first worker to acquire the lock
    boots and owns the container; the rest read its connection info from the state
    file. The owner stops the container only after every worker has released it.
    """
    lock = FileLock(str(shared_dir / f"{key}.lock"))
    state_path = shared_dir / f"{key}.json"
    owner = False
    container: Any = None

    with lock:
        if state_path.exists():
            state = json.loads(state_path.read_text())
            state["refs"] += 1
            state_path.write_text(json.dumps(state))
            conn: dict[str, Any] = state["conn"]
        else:
            container, conn = boot()
            state_path.write_text(json.dumps({"refs": 1, "conn": conn}))
            owner = True

    try:
        yield conn
    finally:
        with lock:
            state = json.loads(state_path.read_text())
            state["refs"] -= 1
            state_path.write_text(json.dumps(state))
        if owner:
            deadline = time.monotonic() + _OWNER_TEARDOWN_TIMEOUT
            while time.monotonic() < deadline:
                with lock:
                    if json.loads(state_path.read_text())["refs"] <= 0:
                        break
                time.sleep(0.2)
            with contextlib.suppress(Exception):
                container.stop()
            with contextlib.suppress(FileNotFoundError):
                state_path.unlink()


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


# ─── container boot functions (run once, by the owning worker) ────────────────


def _pg_endpoint(host: str, port: int) -> PostgresEndpoint:
    return PostgresEndpoint(
        host=host,
        port=port,
        user=_POSTGRES_USER,
        password=_POSTGRES_PASSWORD,
        base_database=_POSTGRES_BASE_DB,
        dsn_asyncpg_admin=f"postgresql+asyncpg://{_POSTGRES_USER}:{_POSTGRES_PASSWORD}@{host}:{port}/postgres",
        dsn_psycopg_admin=f"postgresql+psycopg://{_POSTGRES_USER}:{_POSTGRES_PASSWORD}@{host}:{port}/postgres",
    )


def _boot_postgres() -> tuple[Any, dict[str, Any]]:
    container = _docker_container(
        IMAGE_POSTGRES,
        ready_log=r"database system is ready to accept connections",
    )
    container.with_env("POSTGRES_USER", _POSTGRES_USER)
    container.with_env("POSTGRES_PASSWORD", _POSTGRES_PASSWORD)
    container.with_env("POSTGRES_DB", _POSTGRES_BASE_DB)
    container.with_exposed_ports(5432)
    container.start()
    host: str = container.get_container_host_ip()
    port: int = int(container.get_exposed_port(5432))
    _wait_for_postgres(_pg_endpoint(host, port))
    return container, {"host": host, "port": port}


def _boot_redis() -> tuple[Any, dict[str, Any]]:
    container = _docker_container(IMAGE_REDIS, ready_log=r"Ready to accept connections")
    container.with_exposed_ports(6379)
    container.start()
    host: str = container.get_container_host_ip()
    port: int = int(container.get_exposed_port(6379))
    return container, {"host": host, "port": port}


def _boot_rabbitmq() -> tuple[Any, dict[str, Any]]:
    container = _docker_container(IMAGE_RABBITMQ, ready_log=r"Server startup complete", timeout=180)
    container.with_exposed_ports(5672, 15672)
    container.start()
    host: str = container.get_container_host_ip()
    amqp_port: int = int(container.get_exposed_port(5672))
    mgmt_port: int = int(container.get_exposed_port(15672))
    _wait_for_rabbitmq(RabbitmqEndpoint(host=host, amqp_port=amqp_port, management_port=mgmt_port))
    return container, {"host": host, "amqp_port": amqp_port, "mgmt_port": mgmt_port}


def _boot_s3() -> tuple[Any, dict[str, Any]]:
    container = _docker_container(IMAGE_MOTO, ready_log=r"Running on http://")
    container.with_exposed_ports(5000)
    container.start()
    host: str = container.get_container_host_ip()
    port: int = int(container.get_exposed_port(5000))
    return container, {"endpoint_url": f"http://{host}:{port}"}


def _boot_mailpit() -> tuple[Any, dict[str, Any]]:
    container = _docker_container(IMAGE_MAILPIT, ready_log=r"accessible via")
    container.with_exposed_ports(1025, 8025)
    container.start()
    host: str = container.get_container_host_ip()
    smtp_port: int = int(container.get_exposed_port(1025))
    api_port: int = int(container.get_exposed_port(8025))
    return container, {"host": host, "smtp_port": smtp_port, "api_url": f"http://{host}:{api_port}"}


# ─── session fixtures (shared container, per-worker isolation) ────────────────


@pytest.fixture(scope="session")
def postgres_endpoint(tmp_path_factory: pytest.TempPathFactory) -> Iterator[PostgresEndpoint]:
    _skip_if_no_docker()
    with _shared_container(_shared_dir(tmp_path_factory), "postgres", _boot_postgres) as conn:
        yield _pg_endpoint(conn["host"], conn["port"])


@pytest.fixture(scope="session")
def template_db(
    postgres_endpoint: PostgresEndpoint, tmp_path_factory: pytest.TempPathFactory
) -> str:
    """Create the template DB once per run (filelock + marker), all migrations applied."""
    shared = _shared_dir(tmp_path_factory)
    lock = FileLock(str(shared / "template.lock"))
    marker = shared / "template.ready"
    with lock:
        if not marker.exists():
            _create_database(postgres_endpoint, _TEMPLATE_DB_NAME)
            _migrate(postgres_endpoint.dsn_asyncpg(_TEMPLATE_DB_NAME))
            marker.write_text("ok")
    return postgres_endpoint.dsn_asyncpg(_TEMPLATE_DB_NAME)


@pytest.fixture
async def fresh_db(postgres_endpoint: PostgresEndpoint, template_db: str) -> AsyncIterator[str]:
    dbname = f"test_{uuid.uuid4().hex[:8]}"
    _create_database(postgres_endpoint, dbname, template=_TEMPLATE_DB_NAME)
    try:
        yield postgres_endpoint.dsn_asyncpg(dbname)
    finally:
        _drop_database(postgres_endpoint, dbname)


@pytest.fixture(scope="session")
def redis_endpoint(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RedisEndpoint]:
    _skip_if_no_docker()
    with _shared_container(_shared_dir(tmp_path_factory), "redis", _boot_redis) as conn:
        yield RedisEndpoint(host=conn["host"], port=conn["port"], db=_worker_db_index())


@pytest.fixture(scope="session")
def rabbitmq_endpoint(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RabbitmqEndpoint]:
    _skip_if_no_docker()
    with _shared_container(_shared_dir(tmp_path_factory), "rabbitmq", _boot_rabbitmq) as conn:
        endpoint = RabbitmqEndpoint(
            host=conn["host"],
            amqp_port=conn["amqp_port"],
            management_port=conn["mgmt_port"],
            vhost=f"test_{_worker_tag()}",
        )
        _ensure_vhost(endpoint)
        try:
            yield endpoint
        finally:
            with contextlib.suppress(Exception):
                _delete_vhost(endpoint)


@pytest.fixture(scope="session")
def s3_endpoint(tmp_path_factory: pytest.TempPathFactory) -> Iterator[S3Endpoint]:
    """Shared moto container; each worker gets its own bucket."""
    _skip_if_no_docker()
    with _shared_container(_shared_dir(tmp_path_factory), "s3", _boot_s3) as conn:
        endpoint = S3Endpoint(
            endpoint_url=conn["endpoint_url"],
            region="us-east-1",
            access_key="testing",
            secret_key="testing",  # moto accepts any credential
            bucket=f"arvel-ecommerce-{_worker_tag()}",
        )
        _ensure_bucket(endpoint)
        yield endpoint


@pytest.fixture(scope="session")
def mailpit_endpoint(tmp_path_factory: pytest.TempPathFactory) -> Iterator[MailpitEndpoint]:
    _skip_if_no_docker()
    with _shared_container(_shared_dir(tmp_path_factory), "mailpit", _boot_mailpit) as conn:
        yield MailpitEndpoint(
            smtp_host=conn["host"], smtp_port=conn["smtp_port"], api_url=conn["api_url"]
        )


# ─── helpers ─────────────────────────────────────────────────────────────────


def _migrate(template_dsn: str) -> None:
    import asyncio

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


def _rabbit_api(endpoint: RabbitmqEndpoint, method: str, path: str, body: Any = None) -> None:
    url = f"http://{endpoint.host}:{endpoint.management_port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)  # noqa: S310 # nosec B310
    req.add_header("Authorization", "Basic " + base64.b64encode(b"guest:guest").decode())
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=5):  # noqa: S310 # nosec B310
        pass


def _ensure_vhost(endpoint: RabbitmqEndpoint) -> None:
    _rabbit_api(endpoint, "PUT", f"/api/vhosts/{endpoint.vhost}")
    _rabbit_api(
        endpoint,
        "PUT",
        f"/api/permissions/{endpoint.vhost}/guest",
        {"configure": ".*", "write": ".*", "read": ".*"},
    )


def _delete_vhost(endpoint: RabbitmqEndpoint) -> None:
    _rabbit_api(endpoint, "DELETE", f"/api/vhosts/{endpoint.vhost}")


def _ensure_bucket(endpoint: S3Endpoint) -> None:
    boto3: Any = importlib.import_module("boto3")
    client: Any = boto3.client(
        "s3",
        endpoint_url=endpoint.endpoint_url,
        region_name=endpoint.region,
        aws_access_key_id=endpoint.access_key,
        aws_secret_access_key=endpoint.secret_key,
    )
    with contextlib.suppress(Exception):
        client.create_bucket(Bucket=endpoint.bucket)


def _wait_for_rabbitmq(endpoint: RabbitmqEndpoint, *, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    url = f"http://{endpoint.host}:{endpoint.management_port}/api/overview"
    auth = "Basic " + base64.b64encode(b"guest:guest").decode()
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
