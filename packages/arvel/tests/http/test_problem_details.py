"""Problem-details handler edge cases."""

from __future__ import annotations

from typing import cast

import httpx
from arvel.http.exceptions import ThrottleException, ValidationException
from arvel.http.problem_details import ProblemDetailsHandler
from fastapi import FastAPI
from starlette.testclient import TestClient


def _client(app: FastAPI) -> httpx.Client:
    ProblemDetailsHandler().register(app)
    return cast("httpx.Client", TestClient(app))


def test_problem_details_uses_exception_details() -> None:
    app = FastAPI()

    @app.get("/boom")
    async def boom() -> None:
        raise ValidationException(
            "Invalid payload",
            details=[{"field": "email", "issue": "taken"}],
        )

    assert boom is not None
    response = _client(app).get("/boom")

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["detail"] == [{"field": "email", "issue": "taken"}]


def test_validation_problem_renders_field_errors() -> None:
    app = FastAPI()

    @app.post("/items")
    async def create_item(quantity: int) -> dict[str, int]:
        return {"quantity": quantity}

    assert create_item is not None
    response = _client(app).post("/items", json={})
    body = response.json()

    assert response.status_code == 422
    assert body["title"] == "Validation failed"
    assert body["type"].endswith("/problems/validation-failed")
    assert isinstance(body["detail"], list)
    assert {"loc", "msg", "type"}.issubset(body["detail"][0])


def test_problem_details_sets_retry_after_for_throttle() -> None:
    app = FastAPI()

    @app.get("/slow")
    async def slow() -> None:
        raise ThrottleException("Slow down", retry_after_seconds=42)

    assert slow is not None
    response = _client(app).get("/slow")

    assert response.status_code == 429
    assert response.headers["retry-after"] == "42"
