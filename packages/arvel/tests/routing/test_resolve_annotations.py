"""Annotation resolution fallback paths in arvel.routing."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import pytest
from arvel.http.requests import FormRequest
from arvel.routing import (
    Route,
    Router,
    _resolve_annotations,  # pyright: ignore[reportPrivateUsage]  # test verifies the shim's private contract
)
from pydantic import BaseModel


def setup_function() -> None:
    Router.reset_singleton()


def test_resolve_falls_back_to_per_param_eval_when_get_type_hints_fails() -> None:
    # Build a handler whose annotation references a name that resolves nowhere.
    # The exec keeps the typechecker from flagging an unresolved name.
    namespace: dict[str, object] = {}
    exec(  # noqa: S102 — intentional dynamic definition for fallback test
        "async def handler(x: 'NoSuchName') -> None:\n    return None\n",
        namespace,
    )
    handler = cast("Callable[..., Any]", namespace["handler"])
    resolved = _resolve_annotations(handler, caller_locals=None)
    # NoSuchName cannot be eval'd anywhere → annotation stays a string.
    assert resolved["x"] == "NoSuchName"


def test_resolve_uses_caller_locals_to_find_closure_scoped_types() -> None:
    class LocalPayload(BaseModel):
        v: int

    async def handler(p: LocalPayload) -> None:
        return None

    resolved = _resolve_annotations(handler, caller_locals=locals())
    assert resolved["p"] is LocalPayload


def test_form_request_without_payload_type_raises_at_registration() -> None:
    # FormRequest declared without [Payload] never captures _payload_type.
    class BadFR(FormRequest):  # type: ignore[type-arg]
        pass

    @Route.post("/bad")
    async def handler(form: BadFR) -> dict[str, str]:
        return {"k": "v"}

    del handler  # registered via @Route.post; drop local binding
    from fastapi import FastAPI

    app = FastAPI()
    with pytest.raises(TypeError, match="did not capture its payload type"):
        Router.singleton().register_with_app(app)
