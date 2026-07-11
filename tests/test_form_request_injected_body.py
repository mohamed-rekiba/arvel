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
        response = client.post("/denied", json={"value": 1}, headers={"accept": "application/json"})
    assert response.status_code == 403


def test_plain_struct_body_is_untouched() -> None:
    # a non-FormRequest Schema keeps the structural-only path: no hooks, no rule engine
    with _client() as client:
        response = client.post("/plain", json={"email": "  RAW@Case "})
    assert response.status_code == 201
    assert response.json() == {"email": "  RAW@Case "}


# --- AR-005/AR-006/DR-0074: the body is decoded in the pipeline, not on the Litestar signature ----


class WidgetBody(FormRequest):
    name: str
    qty: int = 1

    @classmethod
    def rules(cls) -> dict[str, str | list[Any]]:
        return {"name": "required|string"}


async def _via_payload(request: Any, payload: WidgetBody) -> dict[str, Any]:
    return {"name": payload.name, "qty": payload.qty}


async def _via_form(request: Any, form: WidgetBody) -> dict[str, Any]:
    return {"name": form.name}


def test_injected_body_binds_under_any_param_name() -> None:
    # AR-006: the body is matched by type, not by the reserved name `data`; any param name works
    kernel = HttpKernel()
    kernel.post("/via-payload", _via_payload)
    kernel.post("/via-form", _via_form)
    with TestClient(kernel.build()) as client:
        r = client.post("/via-payload", json={"name": "ada", "qty": 3})
        assert r.status_code == 201 and r.json() == {"name": "ada", "qty": 3}
        assert client.post("/via-form", json={"name": "bea"}).status_code == 201


def test_omitted_defaulted_field_passes_its_rule() -> None:
    # rules() see the structurally-decoded payload (defaults filled), so an omitted `qty` doesn't
    # spuriously fail a rule that assumes the field is present (DR-0074 regression guard)
    kernel = HttpKernel()
    kernel.post("/via-payload", _via_payload)
    with TestClient(kernel.build()) as client:
        assert client.post("/via-payload", json={"name": "ada"}).status_code == 201


def test_malformed_body_is_422_not_a_transport_400() -> None:
    kernel = HttpKernel()
    kernel.post("/via-payload", _via_payload)
    with TestClient(kernel.build()) as client:
        r = client.post("/via-payload", json={"name": "ada", "qty": "not-an-int"})
        assert r.status_code == 422  # the framework's uniform validation status


def test_openapi_request_body_is_served_and_exported() -> None:
    # the body isn't on the Litestar signature, so arvel injects its requestBody into both the
    # openapi() export and the served /openapi.json (via the JSON render plugin)
    kernel = HttpKernel()
    kernel.post("/via-payload", _via_payload)
    exported = kernel.openapi()
    op = exported["paths"]["/via-payload"]["post"]
    assert op["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("WidgetBody")
    assert "WidgetBody" in exported["components"]["schemas"]
    with TestClient(kernel.build()) as client:
        served = client.get("/schema/openapi.json").json()
    served_op = served["paths"]["/via-payload"]["post"]
    assert served_op["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "WidgetBody"
    )
