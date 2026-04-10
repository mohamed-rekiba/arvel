"""Health checks — probe database, cache, and queue connectivity."""

from __future__ import annotations

import asyncio
import time

import typer

health_app = typer.Typer(name="health", help="Health check commands.")


@health_app.command("check")
def check() -> None:
    """Probe each subsystem and report pass/fail with timing."""
    results: list[tuple[str, bool, float]] = []

    results.append(_check_database())
    results.append(_check_cache())
    results.append(_check_queue())

    typer.echo(f"\n{'Subsystem':<15} {'Status':<10} {'Time'}")
    typer.echo("-" * 40)

    all_passed = True
    for name, passed, elapsed in results:
        status = "OK" if passed else "FAIL"
        if not passed:
            all_passed = False
        typer.echo(f"{name:<15} {status:<10} {elapsed:.3f}s")

    typer.echo("")
    if all_passed:
        typer.echo("All health checks passed.")
    else:
        typer.echo("Some health checks failed.")
        raise typer.Exit(code=1)


def _check_database() -> tuple[str, bool, float]:
    start = time.monotonic()
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        from arvel.data.config import DatabaseSettings

        settings = DatabaseSettings()

        async def _probe() -> None:
            engine = create_async_engine(settings.url)
            try:
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
            finally:
                await engine.dispose()

        asyncio.run(_probe())
        elapsed = time.monotonic() - start
        return ("Database", True, elapsed)
    except Exception:
        elapsed = time.monotonic() - start
        return ("Database", False, elapsed)


def _check_cache() -> tuple[str, bool, float]:
    start = time.monotonic()
    try:
        from arvel.cache.config import CacheSettings

        settings = CacheSettings()
        driver = settings.driver

        if driver == "memory":
            elapsed = time.monotonic() - start
            return ("Cache", True, elapsed)

        if driver == "redis":
            from typing import Any, cast

            from arvel.cache.drivers.redis_driver import RedisCache

            async def _probe() -> None:
                import redis.asyncio as aioredis

                client = aioredis.from_url(settings.redis_url)
                try:
                    cache = RedisCache(client=cast("Any", client), prefix=settings.prefix)
                    await cache.put("__health__", "ok", ttl=5)
                finally:
                    await client.aclose()

            asyncio.run(_probe())

        elapsed = time.monotonic() - start
        return ("Cache", True, elapsed)
    except Exception:
        elapsed = time.monotonic() - start
        return ("Cache", False, elapsed)


def _check_queue() -> tuple[str, bool, float]:
    from arvel.queue.config import QueueSettings
    from arvel.queue.manager import QueueManager

    start = time.monotonic()
    try:
        settings = QueueSettings()
        manager = QueueManager()
        queue = manager.create_driver(settings)
        asyncio.run(queue.size())
        elapsed = time.monotonic() - start
        return ("Queue", True, elapsed)
    except Exception:
        elapsed = time.monotonic() - start
        return ("Queue", False, elapsed)
