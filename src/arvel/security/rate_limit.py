"""Rate limiting middleware — in-memory sliding window with configurable limits.

Supports per-IP and per-user rate limiting. Uses an in-memory store by default;
can be backed by any cache driver implementing the cache contract (future Epic 007).
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from collections.abc import MutableMapping
    from typing import Any

    from starlette.types import ASGIApp, Receive, Scope, Send


@dataclass
class RateLimitRule:
    """Defines a rate limit: max_requests per window_seconds."""

    max_requests: int
    window_seconds: int

    @classmethod
    def parse(cls, spec: str) -> RateLimitRule:
        """Parse a spec like '5/minute', '100/hour', '10/30s'."""
        parts = spec.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid rate limit spec: {spec}. Expected 'N/period'.")

        max_requests = int(parts[0])
        period = parts[1].strip().lower()

        period_map = {
            "second": 1,
            "s": 1,
            "minute": 60,
            "min": 60,
            "m": 60,
            "hour": 3600,
            "h": 3600,
            "day": 86400,
            "d": 86400,
        }

        if period in period_map:
            window = period_map[period]
        elif period.endswith("s") and period[:-1].isdigit():
            window = int(period[:-1])
        elif period.isdigit():
            window = int(period)
        else:
            raise ValueError(
                f"Unknown rate limit period: {period}. "
                f"Use: second, minute, hour, day, or Ns (e.g. 30s)."
            )

        return cls(max_requests=max_requests, window_seconds=window)


@dataclass
class _BucketEntry:
    timestamps: list[float] = field(default_factory=list)


class InMemoryRateLimitStore:
    """Sliding-window rate limiter backed by in-memory dicts.

    Not suitable for multi-process deployments — use a cache-backed
    store in production (future cache contract integration).
    """

    def __init__(self) -> None:
        self._buckets: dict[str, _BucketEntry] = defaultdict(_BucketEntry)

    def hit(self, key: str, rule: RateLimitRule) -> tuple[bool, int, int]:
        """Record a request and check the limit.

        Returns (allowed, remaining, retry_after_seconds).
        """
        now = time.monotonic()
        entry = self._buckets[key]
        window_start = now - rule.window_seconds

        entry.timestamps = [t for t in entry.timestamps if t > window_start]
        current_count = len(entry.timestamps)

        if current_count >= rule.max_requests:
            oldest_in_window = entry.timestamps[0] if entry.timestamps else now
            retry_after = int(oldest_in_window - window_start) + 1
            return False, 0, max(retry_after, 1)

        entry.timestamps.append(now)
        remaining = rule.max_requests - len(entry.timestamps)
        return True, remaining, 0

    def reset(self, key: str) -> None:
        self._buckets.pop(key, None)


class RateLimitMiddleware:
    """ASGI middleware that enforces rate limits per-IP (and per-user if authenticated).

    Adds standard rate limit headers to all responses:
    - ``X-RateLimit-Limit``
    - ``X-RateLimit-Remaining``
    - ``Retry-After`` (on 429 only)
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        rule: RateLimitRule,
        store: InMemoryRateLimitStore | None = None,
        key_prefix: str = "rl",
        exclude_paths: set[str] | None = None,
    ) -> None:
        self.app = app
        self._rule = rule
        self._store = store or InMemoryRateLimitStore()
        self._key_prefix = key_prefix
        self._exclude_paths = exclude_paths or set()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in self._exclude_paths:
            await self.app(scope, receive, send)
            return

        client_ip = self._extract_ip(scope)
        state = scope.get("state", {})
        user_id = state.get("auth_user_id")
        key_suffix = f"{user_id}:{client_ip}" if user_id else client_ip
        key = f"{self._key_prefix}:{key_suffix}"

        allowed, remaining, retry_after = self._store.hit(key, self._rule)

        if not allowed:
            response = JSONResponse(
                {
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Too many requests",
                    }
                },
                status_code=429,
                headers={
                    "X-RateLimit-Limit": str(self._rule.max_requests),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": str(retry_after),
                },
            )
            await response(scope, receive, send)
            return

        async def send_with_headers(message: MutableMapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-ratelimit-limit", str(self._rule.max_requests).encode()))
                headers.append((b"x-ratelimit-remaining", str(remaining).encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)

    def _extract_ip(self, scope: Scope) -> str:
        """Extract client IP from ASGI scope, preferring X-Forwarded-For."""
        headers = dict(scope.get("headers", []))
        forwarded = headers.get(b"x-forwarded-for", b"").decode("latin-1")
        if forwarded:
            return forwarded.split(",")[0].strip()
        client = scope.get("client")
        if client:
            return client[0]
        return "unknown"
