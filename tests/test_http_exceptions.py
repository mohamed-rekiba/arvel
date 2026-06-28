"""C4b — FormRequest validation wiring + content-negotiated exception rendering."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.validation import FormRequest


class CreateUser(FormRequest):
    name: str
    age: int


class GuardedForm(FormRequest):
    value: int

    def authorize(self) -> bool:
        return False


async def _store(request: Any) -> dict[str, Any]:
    form = await request.validate(CreateUser)
    return {"name": form.name, "age": form.age}


async def _guarded(request: Any) -> dict[str, Any]:
    await request.validate(GuardedForm)
    return {"ok": True}


def _client() -> TestClient[Any]:
    kernel = HttpKernel()
    kernel.post("/users", _store)
    kernel.post("/guarded", _guarded)
    return TestClient(kernel.build())


def test_valid_form_passes() -> None:
    with _client() as client:
        response = client.post("/users", json={"name": "ada", "age": 36})
    assert response.status_code == 201
    assert response.json() == {"name": "ada", "age": 36}


def test_invalid_form_renders_422_json() -> None:
    with _client() as client:
        response = client.post(
            "/users", json={"name": "ada"}, headers={"accept": "application/json"}
        )
    assert response.status_code == 422
    body = response.json()
    assert body["message"] == "Unprocessable Entity"
    assert "errors" in body


def test_invalid_form_redirects_back_for_browser() -> None:
    # web clients (text/html) get a redirect-back, not a JSON 422 (doc 10 content negotiation)
    with _client() as client:
        response = client.post(
            "/users",
            json={"name": "ada"},
            headers={"accept": "text/html"},
            follow_redirects=False,
        )
    assert response.status_code == 302
    assert "location" in response.headers


def test_failed_authorize_renders_403() -> None:
    with _client() as client:
        response = client.post("/guarded", json={"value": 1})
    assert response.status_code == 403
