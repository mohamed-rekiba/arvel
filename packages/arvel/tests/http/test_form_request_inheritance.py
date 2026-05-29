"""FormRequest payload-type inference through multi-level subclassing."""

from __future__ import annotations

from typing import Any

import pytest
from arvel.http.requests import FormRequest
from pydantic import BaseModel


class StorePayload(BaseModel):
    name: str


class StoreRequest(FormRequest[StorePayload]):
    """Direct subclass — should capture StorePayload."""


class StoreRequestWithAuth(StoreRequest):
    """Grandchild subclass — should inherit StorePayload through __mro__."""

    async def authorize(self, request: Any) -> bool:
        return False


def test_direct_subclass_captures_payload_type() -> None:
    assert StoreRequest._payload_type is StorePayload  # pyright: ignore[reportPrivateUsage]  # test asserts the private MRO capture invariant


def test_grandchild_inherits_payload_type_via_mro() -> None:
    assert StoreRequestWithAuth._payload_type is StorePayload  # pyright: ignore[reportPrivateUsage]  # test asserts the private MRO capture invariant


@pytest.mark.asyncio
async def test_authorize_default_denies() -> None:
    # Deny-by-default — subclasses must explicitly grant access (OWASP A01).
    fr = StoreRequest(StorePayload(name="ada"))
    assert await fr.authorize(request=object()) is False


@pytest.mark.asyncio
async def test_authorize_override_takes_effect() -> None:
    fr = StoreRequestWithAuth(StorePayload(name="ada"))
    assert await fr.authorize(request=object()) is False


def test_validated_returns_typed_payload() -> None:
    fr = StoreRequest(StorePayload(name="grace"))
    payload = fr.validated()
    assert payload.name == "grace"
