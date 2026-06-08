"""Prometheus metrics route behavior."""

from __future__ import annotations

import httpx2 as httpx
from arvel.observability.metrics_route import add_metrics_route
from fastapi import FastAPI


async def test_metrics_route_rejects_disallowed_clients() -> None:
    app = FastAPI()
    add_metrics_route(app, allowed_cidrs=["10.0.0.0/8"])

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/_metrics")

    assert response.status_code == 403
    assert response.text == "Forbidden"


async def test_metrics_route_ignores_spoofed_forwarded_header() -> None:
    # Peer is loopback; the allowlist is a public test net. A spoofed XFF that
    # claims an allowlisted IP must NOT pass the guard without a trusted proxy.
    app = FastAPI()
    add_metrics_route(app, allowed_cidrs=["bad-cidr", "203.0.113.0/24"])

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/_metrics", headers={"X-Forwarded-For": "203.0.113.9"})

    assert response.status_code == 403


async def test_metrics_route_honors_forwarded_header_behind_trusted_proxy() -> None:
    # The loopback peer is a declared trusted proxy, so the real client from XFF
    # is used for the CIDR check (bad entries are skipped, not fatal).
    app = FastAPI()
    add_metrics_route(
        app,
        allowed_cidrs=["bad-cidr", "203.0.113.0/24"],
        trusted_proxies=["127.0.0.1/32"],
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/_metrics", headers={"X-Forwarded-For": "203.0.113.9"})

    assert response.status_code == 200
    assert response.text
