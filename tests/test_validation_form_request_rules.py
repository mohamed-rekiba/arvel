"""Spec 12 §3 (B4) — the FormRequest `rules()`/`messages()`/`attributes()`/`with_validator()`
bridge. Consumer-path proof: a real Litestar route (scaffold → boot → POST), not a bare unit call
— msgspec still owns types; `rules()` adds the semantic layer on the decoded payload, and BOTH a
structural (msgspec) failure and a semantic (rule) failure land in the same 422 `{message,
errors}` shape."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.validation import FormRequest, ValidationException, Validator


class Register(FormRequest):
    """Types in the annotations (msgspec); cross-field semantics in `rules()`."""

    password: str
    password_confirmation: str

    @classmethod
    def rules(cls) -> dict[str, str | list[Any]]:
        return {"password": "confirmed|min:8"}

    @classmethod
    def messages(cls) -> dict[str, str]:
        return {"password.confirmed": "The {field} confirmation must match, exactly."}

    @classmethod
    def attributes(cls) -> dict[str, str]:
        return {"password": "new password"}

    @classmethod
    def with_validator(cls, validator: Validator) -> None:
        validator.after(
            lambda v: (
                v.add_error("password", "no-op after check")
                if v.data.get("password") == "__forbidden__"
                else None
            )
        )


async def _register(request: Any) -> dict[str, Any]:
    data = await request.json()
    form = Register.parse(data)
    return {"ok": True, "password_len": len(form.password)}


def _client() -> TestClient[Any]:
    kernel = HttpKernel()
    kernel.post("/register", _register)
    return TestClient(kernel.build())


def test_structurally_valid_but_semantically_invalid_renders_422_with_rule_message() -> None:
    with _client() as client:
        response = client.post(
            "/register",
            json={"password": "longenough", "password_confirmation": "nope"},
        )
    assert response.status_code == 422
    body = response.json()
    assert "errors" in body
    assert "new password confirmation must match" in body["errors"]["password"][0]


def test_structural_msgspec_error_lands_in_the_same_422_error_bag() -> None:
    with _client() as client:
        # missing `password_confirmation` entirely -> msgspec's own structural failure, not rules()
        response = client.post("/register", json={"password": "longenough"})
    assert response.status_code == 422
    body = response.json()
    assert "message" in body
    assert "errors" in body  # same {message, errors} shape as a rule-engine 422


def test_valid_payload_still_returns_the_typed_struct() -> None:
    with _client() as client:
        response = client.post(
            "/register",
            json={"password": "longenough", "password_confirmation": "longenough"},
        )
    assert response.status_code == 201
    assert response.json() == {"ok": True, "password_len": len("longenough")}


def test_direct_parse_raises_validation_exception_for_rule_failure() -> None:
    try:
        Register.parse({"password": "longenough", "password_confirmation": "nope"})
        raise AssertionError("should have raised")
    except ValidationException as exc:
        assert "password" in exc.errors
