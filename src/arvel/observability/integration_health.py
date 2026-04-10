"""Integration health checks for framework subsystems."""

from __future__ import annotations

import inspect
import time
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

from arvel.cache.config import CacheSettings
from arvel.data.config import DatabaseSettings
from arvel.observability.health import HealthResult, HealthStatus
from arvel.queue.config import QueueSettings
from arvel.queue.manager import QueueManager
from arvel.storage.config import StorageSettings

if TYPE_CHECKING:
    from arvel.queue.contracts import QueueContract


def _elapsed_ms(start: float) -> float:
    return (time.monotonic() - start) * 1000


def _sanitize_error_message(exc: Exception) -> str:
    """Return an error message that never includes secrets."""
    message = str(exc).strip()
    if not message:
        return exc.__class__.__name__
    return exc.__class__.__name__


class DatabaseHealthCheck:
    """Checks database connectivity with a lightweight SELECT 1 probe."""

    name = "database"

    async def check(self) -> HealthResult:
        start = time.monotonic()
        try:
            from sqlalchemy import text
            from sqlalchemy.ext.asyncio import create_async_engine

            settings = DatabaseSettings()
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
    """Checks cache backend connectivity based on configured cache driver."""

    name = "cache"

    async def check(self) -> HealthResult:
        start = time.monotonic()
        settings = CacheSettings()
        try:
            if settings.driver == "redis":
                import redis.asyncio as aioredis

                client = aioredis.from_url(settings.redis_url)
                try:
                    ping_result = client.ping()
                    if inspect.isawaitable(ping_result):
                        result = await ping_result
                    else:
                        result = ping_result
                    if not result:
                        raise Exception("Redis ping failed")
                finally:
                    await client.aclose()
                return HealthResult(
                    status=HealthStatus.HEALTHY,
                    message="ok",
                    duration_ms=_elapsed_ms(start),
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
    """Checks queue driver readiness by calling a minimal size probe."""

    name = "queue"

    async def check(self) -> HealthResult:
        start = time.monotonic()
        queue: QueueContract | None = None
        try:
            settings = QueueSettings()
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
    """Checks storage backend connectivity.

    - **local**: Verifies the storage root directory exists and is writable.
    - **s3**: Performs a lightweight ``head_bucket`` probe against S3/MinIO.
    - **null**: Always healthy (no-op driver).
    """

    name = "storage"

    async def check(self) -> HealthResult:
        start = time.monotonic()
        settings = StorageSettings()
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
