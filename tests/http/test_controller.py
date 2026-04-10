"""Tests for Controller DI resolution — Story 3.

FR-031: Controller resolved from Arvel container with constructor DI
FR-032: Path parameters validated and passed via FastAPI
FR-033: Pydantic model body validated before injection
FR-034: Starlette Request injected when type-hinted
FR-035: REQUEST-scoped child container per request, closed after response
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from starlette.testclient import TestClient


class CreateItemRequest(BaseModel):
    name: str
    price: float


class TestControllerDI:
    """FR-031: Controller class resolved from container with constructor injection."""

    async def test_controller_receives_injected_service(
        self, http_app_with_controller: Any
    ) -> None:
        app = http_app_with_controller
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/items")
        assert response.status_code == 200
        body = response.json()
        assert body["service_injected"] is True

    async def test_controller_method_called(self, http_app_with_controller: Any) -> None:
        app = http_app_with_controller
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/items")
        assert response.status_code == 200


class TestPathParameters:
    """FR-032: Path parameters validated by FastAPI."""

    async def test_valid_int_path_param(self, http_app_with_controller: Any) -> None:
        app = http_app_with_controller
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/items/42")
        assert response.status_code == 200
        body = response.json()
        assert body["item_id"] == 42

    async def test_invalid_path_param_returns_422(self, http_app_with_controller: Any) -> None:
        app = http_app_with_controller
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/items/abc")
        assert response.status_code == 422


class TestRequestBodyValidation:
    """FR-033: Pydantic model body validated before controller injection."""

    async def test_valid_body_deserialized(self, http_app_with_controller: Any) -> None:
        app = http_app_with_controller
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post("/items", json={"name": "Widget", "price": 9.99})
        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Widget"
        assert body["price"] == 9.99

    async def test_invalid_body_returns_422(self, http_app_with_controller: Any) -> None:
        app = http_app_with_controller
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post("/items", json={"name": 123})
        assert response.status_code == 422

    async def test_missing_required_field_returns_422(self, http_app_with_controller: Any) -> None:
        app = http_app_with_controller
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post("/items", json={})
        assert response.status_code == 422


class TestRequestInjection:
    """FR-034: Starlette Request injected when type-hinted."""

    async def test_request_object_injected(self, http_app_with_controller: Any) -> None:
        app = http_app_with_controller
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/request-info")
        assert response.status_code == 200
        body = response.json()
        assert body["method"] == "GET"
        assert "/request-info" in body["url"]


class TestRequestScopedContainer:
    """FR-035: REQUEST-scoped child container created and closed per request."""

    async def test_request_scoped_services_are_independent(
        self, http_app_with_scoped_service: Any
    ) -> None:
        app, _close_log = http_app_with_scoped_service
        client = TestClient(app, raise_server_exceptions=False)

        response_1 = client.get("/scoped-id")
        response_2 = client.get("/scoped-id")

        assert response_1.status_code == 200
        assert response_2.status_code == 200

        id_1 = response_1.json()["instance_id"]
        id_2 = response_2.json()["instance_id"]

        assert id_1 != id_2

    async def test_container_closed_after_request(self, http_app_with_scoped_service: Any) -> None:
        app, close_log = http_app_with_scoped_service
        client = TestClient(app, raise_server_exceptions=False)

        client.get("/scoped-id")

        assert len(close_log) > 0
