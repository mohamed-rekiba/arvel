"""Redis driver — composite ZSET design with atomic Lua promote-and-pop.

 replaced the original single-list RPUSH/BLPOP design so the driver
honours both ``envelope.delay`` and ``envelope.priority`` natively:

- ``<queue_key>:<queue>:scheduled`` ZSET (score = ``available_at_ms``) holds
 envelopes that are not yet due.
- ``<queue_key>:<queue>:ready`` ZSET holds envelopes that are due now. The
 score is ``-priority * _PRIORITY_SCALE + enqueue_ms`` so ``ZPOPMIN`` returns
 the highest priority first and, within one priority, the earliest enqueued
 (FIFO). ``_PRIORITY_SCALE`` is wider than any millisecond timestamp, so
 priority always dominates the time tiebreaker.
- An atomic Lua script (``promote_and_pop.lua``) moves due-now entries
 from ``:scheduled`` into ``:ready`` and ``ZPOPMIN``s one in a single
 round trip — guaranteeing no double-dispatch under concurrent workers.
"""

from __future__ import annotations

import asyncio
import importlib
import time
from typing import Any, Protocol, cast

from arvel.logging.facade import Log
from arvel.queue.config import RedisQueueConfig
from arvel.queue.drivers._redis_lua import PROMOTE_AND_POP_LUA
from arvel.queue.envelope import JobEnvelope

logger = Log.channel(__name__)

# Each priority band is this many score units wide. A band must be wider than
# any millisecond timestamp it carries so priority always outranks the time
# tiebreaker. 1e13 ms ≈ year 2286, and max score (priority 9) stays ~9.2e13 —
# well under float64's exact-integer ceiling (2^53), so ms diffs stay exact.
# Mirrored in promote_and_pop.lua; keep both in sync.
_PRIORITY_SCALE = 10**13


class RedisQueueConn(Protocol):
    """Minimal interface of redis.asyncio.Redis used by RedisConnection.

    Public so that test fakes can ``cast`` to it without importing private names
    (per ``enforce-quality-gates.mdc``).
    """

    async def zadd(self, name: str, mapping: dict[str | bytes, float]) -> int: ...
    async def zcard(self, name: str) -> int: ...
    async def delete(self, *names: str) -> int: ...
    async def script_load(self, script: str) -> str: ...
    async def evalsha(self, sha: str, numkeys: int, *args: Any) -> Any: ...
    async def aclose(self) -> None: ...


class RedisConnection:
    """Composite ZSET driver with Lua promote-and-pop."""

    def __init__(self, config: RedisQueueConfig) -> None:
        self._config = config
        self._redis: RedisQueueConn | None = None
        self._script_sha: str | None = None
        # Strictly increasing per-process tiebreaker. Rapid pushes can land in
        # the same millisecond; bumping past the last value keeps them FIFO.
        self._last_ready_ms = 0

    def _client(self) -> RedisQueueConn:
        if self._redis is None:
            try:
                _aioredis = importlib.import_module("redis.asyncio")
            except ImportError as exc:
                raise ImportError(
                    "arvel[redis] requires 'redis'. Install with: pip install arvel[redis]"
                ) from exc
            self._redis = cast(
                "RedisQueueConn",
                _aioredis.Redis(
                    host=self._config.host,
                    port=self._config.port,
                    db=self._config.db,
                    password=self._config.password.get_secret_value() or None,
                    decode_responses=False,
                ),
            )
        return self._redis

    async def _ensure_script_loaded(self) -> str:
        if self._script_sha is None:
            self._script_sha = await self._client().script_load(PROMOTE_AND_POP_LUA)
        return self._script_sha

    async def push(self, envelope: JobEnvelope, queue: str = "default") -> None:
        member = envelope.to_json()
        now_ms = int(time.time() * 1000)
        if envelope.delay > 0:
            available_at_ms = now_ms + envelope.delay * 1000
            await self._client().zadd(self._scheduled_key(queue), {member: available_at_ms})
        else:
            score = self._ready_score(envelope.priority, now_ms)
            await self._client().zadd(self._ready_key(queue), {member: score})

    def _ready_score(self, priority: int, now_ms: int) -> int:
        """Composite ready-set score: priority first, enqueue time as tiebreaker."""
        enqueue_ms = max(now_ms, self._last_ready_ms + 1)
        self._last_ready_ms = enqueue_ms
        return -priority * _PRIORITY_SCALE + enqueue_ms

    async def pop_blocking(
        self, queue: str = "default", timeout: float = 3.0
    ) -> JobEnvelope | None:
        """Poll-based pop: tries the Lua script, sleeps briefly on misses, retries until timeout.

        We trade BLPOP's tight wait semantics for ZPOPMIN's atomicity +
        priority correctness. The worker loop already polls so this is no
        regression in practice. NOSCRIPT (Redis restart between
        ``script_load`` and ``evalsha``) is recovered by re-loading the
        script once per attempt.
        """
        deadline = time.monotonic() + max(0.0, timeout)
        poll_interval = 0.05
        while True:
            now_ms = int(time.time() * 1000)
            raw = await self._evalsha_with_reload(queue, now_ms)
            if raw is not None:
                raw_str = raw.decode() if isinstance(raw, bytes) else str(raw)
                try:
                    return JobEnvelope.from_json(raw_str)
                except (ValueError, TypeError) as exc:
                    logger.warning(
                        "queue.envelope.malformed",
                        driver="redis",
                        queue=queue,
                        payload_size=len(raw_str),
                        exception_type=type(exc).__name__,
                        reason=str(exc),
                    )
                    return None
            if time.monotonic() >= deadline:
                return None
            await asyncio.sleep(poll_interval)

    async def _evalsha_with_reload(self, queue: str, now_ms: int) -> Any:
        """Run the Lua script; reload + retry once if Redis dropped the cached SHA.

        ``redis.exceptions.NoScriptError`` is raised when the cached SHA is
        unknown (typical after a Redis restart or FLUSHALL). We invalidate
        our cached SHA, re-load, and try once more before propagating.
        """
        sha = await self._ensure_script_loaded()
        try:
            return await self._client().evalsha(
                sha,
                2,
                self._scheduled_key(queue),
                self._ready_key(queue),
                now_ms,
            )
        except Exception as exc:
            if "NOSCRIPT" not in str(exc):
                raise
            self._script_sha = None
            sha = await self._ensure_script_loaded()
            return await self._client().evalsha(
                sha,
                2,
                self._scheduled_key(queue),
                self._ready_key(queue),
                now_ms,
            )

    async def size(self, queue: str = "default") -> int:
        ready = int(await self._client().zcard(self._ready_key(queue)))
        scheduled = int(await self._client().zcard(self._scheduled_key(queue)))
        return ready + scheduled

    async def clear(self, queue: str = "default") -> None:
        await self._client().delete(self._ready_key(queue), self._scheduled_key(queue))

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    def _ready_key(self, queue: str) -> str:
        return f"{self._config.queue_key}:{queue}:ready"

    def _scheduled_key(self, queue: str) -> str:
        return f"{self._config.queue_key}:{queue}:scheduled"


__all__ = ["RedisConnection"]
