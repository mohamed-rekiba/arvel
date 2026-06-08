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


async def test_metrics_route_allows_forwarded_clients_and_bad_cidrs() -> None:
    app = FastAPI()
    add_metrics_route(app, allowed_cidrs=["bad-cidr", "203.0.113.0/24"])

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/_metrics", headers={"X-Forwarded-For": "203.0.113.9"})

    assert response.status_code == 200
    assert response.text
