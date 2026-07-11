"""An injected FormRequest-typed body param runs the full lifecycle (parity: type-hinting a
form request in a handler signature IS the validation trigger — no manual request.validate()).

The lifecycle runs in the pipeline destination, after every middleware, so a rules() 422 can
never leak information past an Authenticate/Authorize denial (DR-0054's ordering argument).
"""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.validation import FormRequest, Schema


class Signup(FormRequest):
    email: str
    password: str

    @classmethod
    def prepare_for_validation(cls, data: dict[str, Any]) -> dict[str, Any]:
        data["email"] = str(data.get("email", "")).strip().lower()
        return data

    @classmethod
    def rules(cls) -> dict[str, str | list[Any]]:
        return {"email": "required|email", "password": "required|string|min:8"}


class Denied(FormRequest):
    value: int

    def authorize(self) -> bool:
        return False


class PlainBody(Schema):
    email: str


async def _signup(request: Any, data: Signup) -> dict[str, Any]:
    return {"email": data.email}


async def _denied(request: Any, data: Denied) -> dict[str, Any]:
    return {"ok": True}


async def _plain(request: Any, data: PlainBody) -> dict[str, Any]:
    return {"email": data.email}


def _client() -> TestClient[Any]:
    kernel = HttpKernel()
    kernel.post("/signup", _signup)
    kernel.post("/denied", _denied)
    kernel.post("/plain", _plain)
    return TestClient(kernel.build())


def test_injected_form_request_runs_rules() -> None:
    with _client() as client:
        response = client.post(
            "/signup",
            json={"email": "not-an-email", "password": "short"},
            headers={"accept": "application/json"},
        )
    assert response.status_code == 422
    errors = response.json()["errors"]
    assert "email" in errors and "password" in errors


def test_injected_form_request_runs_prepare_hook() -> None:
    with _client() as client:
        response = client.post(
            "/signup", json={"email": "  Ada@Example.COM ", "password": "long-enough"}
        )
    assert response.status_code == 201
    assert response.json() == {"email": "ada@example.com"}


def test_injected_form_request_honours_authorize() -> None:
    with _client() as client:
        response = client.post(
            "/denied", json={"value": 1}, headers={"accept": "application/json"}
        )
    assert response.status_code == 403


def test_plain_struct_body_is_untouched() -> None:
    # a non-FormRequest Schema keeps the structural-only path: no hooks, no rule engine
    with _client() as client:
        response = client.post("/plain", json={"email": "  RAW@Case "})
    assert response.status_code == 201
    assert response.json() == {"email": "  RAW@Case "}
