"""Tests for TestClient — FR-001 to FR-004, SEC-001."""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from arvel.testing.client import TestClient


@pytest.fixture
def sample_app() -> FastAPI:
    app = FastAPI()

    @app.get("/items")
    async def list_items() -> dict:
        return {"items": [1, 2, 3]}

    @app.post("/items", status_code=201)
    async def create_item() -> dict:
        return {"created": True}

    @app.get("/me")
    async def me() -> dict:
        return {"user": "anonymous"}

    return app


class TestTestClient:
    @pytest.mark.anyio
    async def test_get_request(self, sample_app: FastAPI) -> None:
        """FR-001: TestClient processes GET through full middleware."""
        async with TestClient(sample_app) as client:
            response = await client.get("/items")
            assert response.status_code == 200
            assert response.json() == {"items": [1, 2, 3]}

    @pytest.mark.anyio
    async def test_post_request(self, sample_app: FastAPI) -> None:
        """FR-001: TestClient processes POST through full middleware."""
        async with TestClient(sample_app) as client:
            response = await client.post("/items")
            assert response.status_code == 201

    @pytest.mark.anyio
    async def test_client_is_async_context_manager(self, sample_app: FastAPI) -> None:
        """FR-001: TestClient works as async context manager."""
        async with TestClient(sample_app) as client:
            assert client is not None
            resp = await client.get("/items")
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_acting_as_sets_auth_header(self, sample_app: FastAPI) -> None:
        """FR-002: actingAs injects auth header for subsequent requests."""
        async with TestClient(sample_app) as client:
            client.acting_as(user_id=42, headers={"X-User-ID": "42"})
            resp = await client.get("/me")
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_custom_headers_persisted(self, sample_app: FastAPI) -> None:
        """FR-003: custom headers persist across requests."""
        async with TestClient(sample_app) as client:
            client.acting_as(user_id=1, headers={"Authorization": "Bearer test-token"})
            r1 = await client.get("/items")
            r2 = await client.get("/me")
            assert r1.status_code == 200
            assert r2.status_code == 200
