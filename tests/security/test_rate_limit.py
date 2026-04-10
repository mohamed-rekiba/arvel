"""Tests for rate limiting middleware."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from arvel.security.rate_limit import (
    InMemoryRateLimitStore,
    RateLimitMiddleware,
    RateLimitRule,
)

if TYPE_CHECKING:
    from starlette.requests import Request


class TestRateLimitRule:
    def test_parse_per_minute(self) -> None:
        rule = RateLimitRule.parse("5/minute")
        assert rule.max_requests == 5
        assert rule.window_seconds == 60

    def test_parse_per_hour(self) -> None:
        rule = RateLimitRule.parse("100/hour")
        assert rule.max_requests == 100
        assert rule.window_seconds == 3600

    def test_parse_per_second(self) -> None:
        rule = RateLimitRule.parse("10/second")
        assert rule.max_requests == 10
        assert rule.window_seconds == 1

    def test_parse_per_day(self) -> None:
        rule = RateLimitRule.parse("1000/day")
        assert rule.max_requests == 1000
        assert rule.window_seconds == 86400

    def test_parse_custom_seconds(self) -> None:
        rule = RateLimitRule.parse("10/30s")
        assert rule.max_requests == 10
        assert rule.window_seconds == 30

    def test_parse_short_aliases(self) -> None:
        for spec, expected in [("5/s", 1), ("5/m", 60), ("5/h", 3600), ("5/d", 86400)]:
            rule = RateLimitRule.parse(spec)
            assert rule.window_seconds == expected

    def test_parse_invalid_format(self) -> None:
        with pytest.raises(ValueError, match="Invalid rate limit spec"):
            RateLimitRule.parse("bad")

    def test_parse_unknown_period(self) -> None:
        with pytest.raises(ValueError, match="Unknown rate limit period"):
            RateLimitRule.parse("5/fortnight")


class TestInMemoryStore:
    def test_allows_within_limit(self) -> None:
        store = InMemoryRateLimitStore()
        rule = RateLimitRule(max_requests=3, window_seconds=60)

        for i in range(3):
            allowed, remaining, _ = store.hit("key1", rule)
            assert allowed is True
            assert remaining == 3 - (i + 1)

    def test_blocks_over_limit(self) -> None:
        store = InMemoryRateLimitStore()
        rule = RateLimitRule(max_requests=2, window_seconds=60)

        store.hit("key1", rule)
        store.hit("key1", rule)
        allowed, remaining, retry_after = store.hit("key1", rule)

        assert allowed is False
        assert remaining == 0
        assert retry_after >= 1

    def test_different_keys_are_independent(self) -> None:
        store = InMemoryRateLimitStore()
        rule = RateLimitRule(max_requests=1, window_seconds=60)

        allowed1, _, _ = store.hit("key1", rule)
        allowed2, _, _ = store.hit("key2", rule)

        assert allowed1 is True
        assert allowed2 is True

    def test_reset_clears_key(self) -> None:
        store = InMemoryRateLimitStore()
        rule = RateLimitRule(max_requests=1, window_seconds=60)

        store.hit("key1", rule)
        allowed, _, _ = store.hit("key1", rule)
        assert allowed is False

        store.reset("key1")
        allowed, _, _ = store.hit("key1", rule)
        assert allowed is True


async def _echo(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def _create_app(
    rule: str = "3/minute",
    exclude_paths: set[str] | None = None,
) -> Starlette:
    app = Starlette(
        routes=[
            Route("/test", _echo, methods=["GET", "POST"]),
            Route("/health", _echo, methods=["GET"]),
        ],
    )
    app.add_middleware(
        RateLimitMiddleware,
        rule=RateLimitRule.parse(rule),
        exclude_paths=exclude_paths,
    )
    return app


class TestRateLimitMiddleware:
    def test_allows_requests_within_limit(self) -> None:
        client = TestClient(_create_app("3/minute"))
        for _ in range(3):
            resp = client.get("/test")
            assert resp.status_code == 200
            assert "x-ratelimit-limit" in resp.headers
            assert resp.headers["x-ratelimit-limit"] == "3"

    def test_blocks_over_limit(self) -> None:
        client = TestClient(_create_app("2/minute"))
        client.get("/test")
        client.get("/test")
        resp = client.get("/test")

        assert resp.status_code == 429
        body = resp.json()
        assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"
        assert "retry-after" in resp.headers

    def test_rate_limit_headers_present(self) -> None:
        client = TestClient(_create_app("5/minute"))
        resp = client.get("/test")
        assert resp.headers["x-ratelimit-limit"] == "5"
        assert int(resp.headers["x-ratelimit-remaining"]) >= 0

    def test_excluded_paths_bypass(self) -> None:
        client = TestClient(_create_app("1/minute", exclude_paths={"/health"}))
        client.get("/health")
        client.get("/health")
        resp = client.get("/health")
        assert resp.status_code == 200
