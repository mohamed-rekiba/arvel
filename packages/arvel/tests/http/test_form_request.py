"""FormRequest validation + authorize + FastAPI binding."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, EmailStr


class StoreUserPayload(BaseModel):
    email: EmailStr
    password: str


def test_form_request_is_generic() -> None:
    from arvel.http.requests import FormRequest

    StoreUser = FormRequest[StoreUserPayload]
    assert StoreUser is not None


def test_form_request_validated_returns_parsed_payload() -> None:
    from arvel.http.requests import FormRequest

    payload = StoreUserPayload(email="x@example.com", password="hunter2")
    form: FormRequest[StoreUserPayload] = FormRequest(payload)
    assert form.validated() == payload
    assert form.validated().email == "x@example.com"


@pytest.mark.asyncio
async def test_form_request_authorize_default_denies() -> None:
    from arvel.http.requests import FormRequest

    payload = StoreUserPayload(email="x@example.com", password="hunter2")
    form: FormRequest[StoreUserPayload] = FormRequest(payload)

    # Default authorize() returns False — deny-by-default (OWASP A01).
    result = await form.authorize(_FakeRequest())
    assert result is False


@pytest.mark.asyncio
async def test_form_request_authorize_override_can_deny() -> None:
    from arvel.http.requests import FormRequest

    class Denied(FormRequest[StoreUserPayload]):
        async def authorize(self, request: Any) -> bool:
            return False

    payload = StoreUserPayload(email="x@example.com", password="hunter2")
    form = Denied(payload)
    assert (await form.authorize(_FakeRequest())) is False


def test_form_request_bad_body_returns_422_via_fastapi() -> None:
    from arvel.http.exceptions import HttpExceptionHandler
    from arvel.http.requests import FormRequest
    from arvel.routing import Route, Router
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    Router.reset_singleton()

    class StoreUserRequest(FormRequest[StoreUserPayload]):
        pass

    @Route.post("/users")
    async def store(form: StoreUserRequest) -> dict[str, Any]:
        return {"ok": True, "email": form.validated().email}

    del store  # registered via @Route.post; drop local binding
    app = FastAPI()
    HttpExceptionHandler().register(app)
    Router.singleton().register_with_app(app)

    resp = TestClient(app).post("/users", json={"email": "not-an-email"})
    assert resp.status_code == 422
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == "VALIDATION_FAILED"


def test_form_request_authorize_false_returns_403() -> None:
    from arvel.http.exceptions import HttpExceptionHandler
    from arvel.http.requests import FormRequest
    from arvel.routing import Route, Router
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    Router.reset_singleton()

    class StoreUserRequest(FormRequest[StoreUserPayload]):
        async def authorize(self, request: Any) -> bool:
            return False

    @Route.post("/users")
    async def store(form: StoreUserRequest) -> dict[str, Any]:
        return {"ok": True}

    del store  # registered via @Route.post; drop local binding
    app = FastAPI()
    HttpExceptionHandler().register(app)
    Router.singleton().register_with_app(app)

    resp = TestClient(app).post("/users", json={"email": "x@example.com", "password": "hunter2"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


def test_form_request_authorize_runs_after_validation() -> None:
    """Validation errors take precedence over authorize() — 422 not 403."""
    from arvel.http.exceptions import HttpExceptionHandler
    from arvel.http.requests import FormRequest
    from arvel.routing import Route, Router
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    Router.reset_singleton()

    class StoreUserRequest(FormRequest[StoreUserPayload]):
        async def authorize(self, request: Any) -> bool:
            return False  # would deny

    @Route.post("/users")
    async def store(form: StoreUserRequest) -> dict[str, Any]:
        return {"ok": True}

    del store  # registered via @Route.post; drop local binding
    app = FastAPI()
    HttpExceptionHandler().register(app)
    Router.singleton().register_with_app(app)

    resp = TestClient(app).post("/users", json={"email": "bad"})
    assert resp.status_code == 422


class _FakeRequest:
    """Minimal stand-in for starlette.Request when we don't need its plumbing."""

    state: Any = None
