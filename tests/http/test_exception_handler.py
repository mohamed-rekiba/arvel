"""Tests for RFC 9457 Problem Details exception handling.

FR-038: Error responses conform to RFC 9457 Problem Details format
NFR-015: Production errors don't expose internals (stack traces, SQL, paths)
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from arvel.http.exception_handler import install_exception_handlers, register_exception
from arvel.testing.client import TestClient as AsyncTestClient


class TestProblemDetailsFormat:
    """FR-038: RFC 9457 Problem Details JSON format."""

    async def test_404_returns_problem_details(self, http_app_basic: Any) -> None:
        app = http_app_basic
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/nonexistent-route")

        assert response.status_code == 404
        body = response.json()
        assert "type" in body
        assert "title" in body
        assert "status" in body
        assert body["status"] == 404

    async def test_422_returns_problem_details_with_field_errors(
        self, http_app_with_controller: Any
    ) -> None:
        app = http_app_with_controller
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post("/items", json={})
        assert response.status_code == 422
        body = response.json()
        assert "status" in body
        assert body["status"] == 422

    async def test_500_returns_problem_details(self, http_app_with_crashing_handler: Any) -> None:
        app = http_app_with_crashing_handler
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/crash")
        assert response.status_code == 500
        body = response.json()
        assert body["status"] == 500
        assert "type" in body
        assert "title" in body


class TestProductionErrorSafety:
    """NFR-015: No internals exposed when APP_DEBUG=false."""

    async def test_production_500_hides_stack_trace(self, http_app_production_mode: Any) -> None:
        app = http_app_production_mode
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/crash")
        body = response.json()

        assert response.status_code == 500
        # Must NOT contain stack trace, file paths, or SQL
        detail = body.get("detail", "")
        assert "Traceback" not in detail
        assert ".py" not in detail
        assert "line " not in detail

    async def test_debug_500_includes_detail(self, http_app_debug_mode: Any) -> None:
        app = http_app_debug_mode
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/crash")
        body = response.json()

        assert response.status_code == 500
        # Debug mode may include more detail
        assert body.get("detail") is not None
        assert len(body["detail"]) > 0


@pytest.fixture
def app_with_domain_errors() -> FastAPI:
    app = FastAPI()
    install_exception_handlers(app, debug=False)
    register_exception(app)

    from arvel.data.exceptions import NotFoundError
    from arvel.security.exceptions import AuthenticationError, AuthorizationError

    @app.get("/not-found")
    async def not_found() -> dict:
        raise NotFoundError("User not found", model_name="User", record_id=42)

    @app.get("/unauthorized")
    async def unauthorized() -> dict:
        raise AuthenticationError("Invalid token")

    @app.get("/forbidden")
    async def forbidden() -> dict:
        raise AuthorizationError("Insufficient permissions")

    @app.get("/ok")
    async def ok() -> dict:
        return {"status": "ok"}

    return app


class TestDomainExceptionMapping:
    @pytest.mark.anyio
    async def test_not_found_returns_404(self, app_with_domain_errors: FastAPI) -> None:
        async with AsyncTestClient(app_with_domain_errors) as client:
            resp = await client.get("/not-found")
            assert resp.status_code == 404
            body = resp.json()
            assert body["type"] == "about:blank"
            assert body["status"] == 404

    @pytest.mark.anyio
    async def test_authentication_error_returns_401(self, app_with_domain_errors: FastAPI) -> None:
        async with AsyncTestClient(app_with_domain_errors) as client:
            resp = await client.get("/unauthorized")
            assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_authorization_error_returns_403(self, app_with_domain_errors: FastAPI) -> None:
        async with AsyncTestClient(app_with_domain_errors) as client:
            resp = await client.get("/forbidden")
            assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_response_is_problem_json(self, app_with_domain_errors: FastAPI) -> None:
        async with AsyncTestClient(app_with_domain_errors) as client:
            resp = await client.get("/not-found")
            assert resp.headers["content-type"] == "application/problem+json"

    @pytest.mark.anyio
    async def test_instance_field_present(self, app_with_domain_errors: FastAPI) -> None:
        async with AsyncTestClient(app_with_domain_errors) as client:
            resp = await client.get("/not-found")
            body = resp.json()
            assert "instance" in body
            assert body["instance"] == "/not-found"
