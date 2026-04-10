"""Health checks for framework subsystems (DB, cache, mail, search, etc.)."""

from __future__ import annotations

import inspect
import time
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

from arvel.broadcasting.config import BroadcastSettings
from arvel.cache.config import CacheSettings
from arvel.data.config import DatabaseSettings
from arvel.lock.config import LockSettings
from arvel.mail.config import MailSettings
from arvel.observability.health import HealthResult, HealthStatus
from arvel.queue.config import QueueSettings
from arvel.queue.manager import QueueManager
from arvel.search.config import SearchSettings
from arvel.storage.config import StorageSettings

if TYPE_CHECKING:
    from arvel.queue.contracts import QueueContract


def _elapsed_ms(start: float) -> float:
    return (time.monotonic() - start) * 1000


def _sanitize_error_message(exc: Exception) -> str:
    """Class name + short message — never leaks secrets like URLs or keys."""
    cls_name = exc.__class__.__name__
    message = str(exc).strip()
    if not message:
        return cls_name
    truncated = message[:120] + "…" if len(message) > 120 else message
    return f"{cls_name}: {truncated}"


async def _redis_ping_check(redis_url: str, start: float) -> HealthResult:
    """Shared Redis PING probe used by cache, broadcast, and lock checks."""
    import redis.asyncio as aioredis

    client = aioredis.from_url(redis_url)
    try:
        ping_result = client.ping()
        if inspect.isawaitable(ping_result):
            result = await ping_result
        else:
            result = ping_result
        if not result:
            msg = "Redis ping failed"
            raise RuntimeError(msg)
    finally:
        await client.aclose()
    return HealthResult(
        status=HealthStatus.HEALTHY,
        message="ok",
        duration_ms=_elapsed_ms(start),
    )


class DatabaseHealthCheck:
    """SELECT 1 probe against the configured database."""

    name = "database"

    def __init__(self, settings: DatabaseSettings | None = None) -> None:
        self._settings = settings

    async def check(self) -> HealthResult:
        start = time.monotonic()
        try:
            from sqlalchemy import text
            from sqlalchemy.ext.asyncio import create_async_engine

            settings = self._settings if self._settings is not None else DatabaseSettings()
            engine = create_async_engine(settings.url)
            try:
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
            finally:
                await engine.dispose()
            return HealthResult(
                status=HealthStatus.HEALTHY,
                message="ok",
                duration_ms=_elapsed_ms(start),
            )
        except Exception as exc:  # pragma: no cover - exercised via integration tests
            return HealthResult(
                status=HealthStatus.UNHEALTHY,
                message=f"unavailable ({_sanitize_error_message(exc)})",
                duration_ms=_elapsed_ms(start),
            )


class CacheHealthCheck:
    """Redis PING against the configured cache backend."""

    name = "cache"

    def __init__(self, settings: CacheSettings | None = None) -> None:
        self._settings = settings

    async def check(self) -> HealthResult:
        start = time.monotonic()
        settings = self._settings if self._settings is not None else CacheSettings()
        try:
            if settings.driver == "redis":
                return await _redis_ping_check(
                    getattr(settings, "redis_url", "redis://localhost:6379/0"),
                    start,
                )

            return HealthResult(
                status=HealthStatus.UNHEALTHY,
                message=f"unsupported driver '{settings.driver}'",
                duration_ms=_elapsed_ms(start),
            )
        except Exception as exc:  # pragma: no cover - exercised via integration tests
            return HealthResult(
                status=HealthStatus.UNHEALTHY,
                message=f"unavailable ({_sanitize_error_message(exc)})",
                duration_ms=_elapsed_ms(start),
            )


class QueueHealthCheck:
    """Queue size probe against the configured driver."""

    name = "queue"

    def __init__(self, settings: QueueSettings | None = None) -> None:
        self._settings = settings

    async def check(self) -> HealthResult:
        start = time.monotonic()
        queue: QueueContract | None = None
        try:
            settings = self._settings if self._settings is not None else QueueSettings()
            manager = QueueManager()
            queue = manager.create_driver(settings)
            await queue.size(settings.default)
            return HealthResult(
                status=HealthStatus.HEALTHY,
                message="ok",
                duration_ms=_elapsed_ms(start),
            )
        except Exception as exc:  # pragma: no cover - exercised via integration tests
            return HealthResult(
                status=HealthStatus.UNHEALTHY,
                message=f"unavailable ({_sanitize_error_message(exc)})",
                duration_ms=_elapsed_ms(start),
            )
        finally:
            if queue is not None:
                close = getattr(queue, "close", None)
                if callable(close):
                    result = close()
                    if inspect.isawaitable(result):
                        await result


class StorageHealthCheck:
    """Local dir check or S3 head_bucket probe."""

    name = "storage"

    def __init__(self, settings: StorageSettings | None = None) -> None:
        self._settings = settings

    async def check(self) -> HealthResult:
        start = time.monotonic()
        settings = self._settings if self._settings is not None else StorageSettings()
        try:
            if settings.driver == "local":
                return self._check_local(settings, start)

            if settings.driver == "s3":
                return await self._check_s3(settings, start)

            return HealthResult(
                status=HealthStatus.UNHEALTHY,
                message=f"unsupported driver '{settings.driver}'",
                duration_ms=_elapsed_ms(start),
            )
        except Exception as exc:  # pragma: no cover - exercised via integration tests
            return HealthResult(
                status=HealthStatus.UNHEALTHY,
                message=f"unavailable ({_sanitize_error_message(exc)})",
                duration_ms=_elapsed_ms(start),
            )

    @staticmethod
    def _check_local(settings: StorageSettings, start: float) -> HealthResult:
        root = Path(settings.local_root)
        if not root.is_dir():
            return HealthResult(
                status=HealthStatus.UNHEALTHY,
                message=f"local root '{settings.local_root}' does not exist",
                duration_ms=_elapsed_ms(start),
            )
        return HealthResult(
            status=HealthStatus.HEALTHY,
            message="ok",
            duration_ms=_elapsed_ms(start),
        )

    @staticmethod
    async def _check_s3(settings: StorageSettings, start: float) -> HealthResult:
        if not settings.s3_bucket:
            return HealthResult(
                status=HealthStatus.UNHEALTHY,
                message="STORAGE_S3_BUCKET not configured",
                duration_ms=_elapsed_ms(start),
            )

        session_module = import_module("aiobotocore.session")
        session = session_module.get_session()

        client_args: dict[str, str] = {"region_name": settings.s3_region}
        if settings.s3_endpoint_url:
            client_args["endpoint_url"] = settings.s3_endpoint_url
        if settings.s3_access_key:
            client_args["aws_access_key_id"] = settings.s3_access_key
        secret = settings.s3_secret_key.get_secret_value()
        if secret:
            client_args["aws_secret_access_key"] = secret

        async with session.create_client("s3", **client_args) as client:
            result = client.head_bucket(Bucket=settings.s3_bucket)
            if inspect.isawaitable(result):
                await result

        return HealthResult(
            status=HealthStatus.HEALTHY,
            message="ok",
            duration_ms=_elapsed_ms(start),
        )


class MailHealthCheck:
    """SMTP connect + quit probe."""

    name = "mail"

    def __init__(self, settings: MailSettings | None = None) -> None:
        self._settings = settings

    async def check(self) -> HealthResult:
        start = time.monotonic()
        settings = self._settings if self._settings is not None else MailSettings()
        try:
            import aiosmtplib

            smtp = aiosmtplib.SMTP(
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                use_tls=settings.smtp_use_tls,
                timeout=5,
            )
            await smtp.connect()
            await smtp.quit()
            return HealthResult(
                status=HealthStatus.HEALTHY,
                message="ok",
                duration_ms=_elapsed_ms(start),
            )
        except ImportError:
            return HealthResult(
                status=HealthStatus.HEALTHY,
                message="aiosmtplib not installed, skipped",
                duration_ms=_elapsed_ms(start),
            )
        except Exception as exc:
            return HealthResult(
                status=HealthStatus.UNHEALTHY,
                message=f"unavailable ({_sanitize_error_message(exc)})",
                duration_ms=_elapsed_ms(start),
            )


class SearchHealthCheck:
    """Meilisearch /health or Elasticsearch /_cluster/health probe."""

    name = "search"

    def __init__(self, settings: SearchSettings | None = None) -> None:
        self._settings = settings

    async def check(self) -> HealthResult:
        start = time.monotonic()
        settings = self._settings if self._settings is not None else SearchSettings()
        try:
            if settings.driver == "meilisearch":
                return await self._check_meilisearch(settings, start)
            if settings.driver == "elasticsearch":
                return await self._check_elasticsearch(settings, start)
            return HealthResult(
                status=HealthStatus.HEALTHY,
                message=f"driver '{settings.driver}' has no external connection",
                duration_ms=_elapsed_ms(start),
            )
        except Exception as exc:
            return HealthResult(
                status=HealthStatus.UNHEALTHY,
                message=f"unavailable ({_sanitize_error_message(exc)})",
                duration_ms=_elapsed_ms(start),
            )

    @staticmethod
    async def _check_meilisearch(settings: SearchSettings, start: float) -> HealthResult:
        import httpx

        url = f"{settings.meilisearch_url.rstrip('/')}/health"
        headers: dict[str, str] = {}
        if settings.meilisearch_key:
            headers["Authorization"] = f"Bearer {settings.meilisearch_key}"
        async with httpx.AsyncClient(timeout=settings.meilisearch_timeout) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                return HealthResult(
                    status=HealthStatus.HEALTHY,
                    message="ok",
                    duration_ms=_elapsed_ms(start),
                )
            return HealthResult(
                status=HealthStatus.UNHEALTHY,
                message=f"HTTP {resp.status_code}",
                duration_ms=_elapsed_ms(start),
            )

    @staticmethod
    async def _check_elasticsearch(settings: SearchSettings, start: float) -> HealthResult:
        import httpx

        host = settings.elasticsearch_hosts.split(",")[0].strip()
        url = f"{host.rstrip('/')}/_cluster/health"
        async with httpx.AsyncClient(
            timeout=5,
            verify=settings.elasticsearch_verify_certs,
        ) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return HealthResult(
                    status=HealthStatus.HEALTHY,
                    message="ok",
                    duration_ms=_elapsed_ms(start),
                )
            return HealthResult(
                status=HealthStatus.UNHEALTHY,
                message=f"HTTP {resp.status_code}",
                duration_ms=_elapsed_ms(start),
            )


class BroadcastHealthCheck:
    """Redis PING on the broadcast backend."""

    name = "broadcast"

    def __init__(self, settings: BroadcastSettings | None = None) -> None:
        self._settings = settings

    async def check(self) -> HealthResult:
        start = time.monotonic()
        settings = self._settings if self._settings is not None else BroadcastSettings()
        try:
            if settings.driver == "redis":
                return await _redis_ping_check(
                    getattr(settings, "redis_url", "redis://localhost:6379/0"),
                    start,
                )
            return HealthResult(
                status=HealthStatus.HEALTHY,
                message=f"driver '{settings.driver}' has no external connection",
                duration_ms=_elapsed_ms(start),
            )
        except Exception as exc:
            return HealthResult(
                status=HealthStatus.UNHEALTHY,
                message=f"unavailable ({_sanitize_error_message(exc)})",
                duration_ms=_elapsed_ms(start),
            )


class LockHealthCheck:
    """Redis PING on the lock backend."""

    name = "lock"

    def __init__(self, settings: LockSettings | None = None) -> None:
        self._settings = settings

    async def check(self) -> HealthResult:
        start = time.monotonic()
        settings = self._settings if self._settings is not None else LockSettings()
        try:
            if settings.driver == "redis":
                return await _redis_ping_check(
                    getattr(settings, "redis_url", "redis://localhost:6379/0"),
                    start,
                )
            return HealthResult(
                status=HealthStatus.HEALTHY,
                message=f"driver '{settings.driver}' has no external connection",
                duration_ms=_elapsed_ms(start),
            )
        except Exception as exc:
            return HealthResult(
                status=HealthStatus.UNHEALTHY,
                message=f"unavailable ({_sanitize_error_message(exc)})",
                duration_ms=_elapsed_ms(start),
            )
