"""WI-arvel-075 — Epic 049 Story 15: conditional sometimes validation."""

from __future__ import annotations

from typing import Any

from arvel.http.exceptions import HttpExceptionHandler
from arvel.http.requests import FormRequest
from arvel.routing import Route, Router
from arvel.validation import Rule, Validator
from fastapi import FastAPI
from pydantic import BaseModel
from starlette.testclient import TestClient


class TestSometimesRule:
    async def test_applies_rules_when_condition_true(self) -> None:
        data = {"payment": "card", "card_number": "123"}
        validator = Validator(data).sometimes(
            "card_number",
            "required|digits:16",
            lambda payload: payload.get("payment") == "card",
        )
        details = await validator.validate({})
        assert len(details) == 1
        assert details[0]["field"] == "card_number"
        assert "16 digits" in details[0]["issue"]

    async def test_skips_rules_when_condition_false(self) -> None:
        data = {"payment": "cash", "card_number": "123"}
        validator = Validator(data).sometimes(
            "card_number",
            "required|digits:16",
            lambda payload: payload.get("payment") == "card",
        )
        details = await validator.validate({})
        assert details == []

    async def test_skips_when_condition_false_even_if_value_missing(self) -> None:
        data = {"payment": "cash"}
        validator = Validator(data).sometimes(
            "card_number",
            "required",
            lambda payload: payload.get("payment") == "card",
        )
        details = await validator.validate({})
        assert details == []

    async def test_rule_sometimes_helper(self) -> None:
        data = {"payment": "card"}
        validator = Validator(data).add(
            Rule.sometimes(
                "card_number",
                ["required", "digits:16"],
                lambda payload: payload.get("payment") == "card",
            )
        )
        details = await validator.validate({})
        assert len(details) == 1
        assert details[0]["field"] == "card_number"

    async def test_pipe_notation_splits_into_multiple_rules(self) -> None:
        data = {"code": "abc"}
        details = await Validator(data).validate({"code": "required|digits:3"})
        assert len(details) == 1
        assert "3 digits" in details[0]["issue"]


class TestFormRequestWithValidator:
    async def test_with_validator_registers_sometimes(self) -> None:
        Router.reset_singleton()

        class Payload(BaseModel):
            payment: str
            card_number: str | None = None

        class PayForm(FormRequest[Payload]):
            async def authorize(self, request: Any) -> bool:
                return True

            def with_validator(self, validator: Validator) -> None:
                validator.sometimes(
                    "card_number",
                    "required|digits:16",
                    lambda data: data.get("payment") == "card",
                )

        @Route.post("/pay")
        async def pay(form: PayForm) -> dict[str, str]:
            payload = form.validated()
            return {"payment": payload.payment}

        del pay
        app = FastAPI()
        HttpExceptionHandler().register(app)
        Router.singleton().register_with_app(app)
        client = TestClient(app)

        cash_resp = client.post("/pay", json={"payment": "cash"})
        assert cash_resp.status_code == 200

        card_resp = client.post("/pay", json={"payment": "card", "card_number": "123"})
        assert card_resp.status_code == 422
        assert card_resp.json()["error"]["code"] == "VALIDATION_FAILED"

    async def test_rules_run_before_authorize(self) -> None:
        Router.reset_singleton()

        class Payload(BaseModel):
            payment: str
            card_number: str | None = None

        class PayForm(FormRequest[Payload]):
            async def authorize(self, request: Any) -> bool:
                return False

            def with_validator(self, validator: Validator) -> None:
                validator.sometimes(
                    "card_number",
                    "required",
                    lambda data: data.get("payment") == "card",
                )

        @Route.post("/pay")
        async def pay(form: PayForm) -> dict[str, str]:
            return {"ok": "true"}

        del pay
        app = FastAPI()
        HttpExceptionHandler().register(app)
        Router.singleton().register_with_app(app)

        resp = TestClient(app).post("/pay", json={"payment": "card"})
        assert resp.status_code == 422
