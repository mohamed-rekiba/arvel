"""Validation (doc 10) — FormRequest authorize() -> 403 enforcement."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.http.request import Request
from arvel.validation import AuthorizationException, FormRequest, ValidationException


class StorePost(FormRequest):
    title: str

    def authorize(self) -> bool:
        return self.title != "forbidden"


def test_authorized_returns_validated_instance() -> None:
    post = StorePost.authorized({"title": "Hello"})
    assert post.title == "Hello"


def test_denied_authorize_raises_403() -> None:
    with pytest.raises(AuthorizationException) as exc:
        StorePost.authorized({"title": "forbidden"})
    assert exc.value.status == 403


def test_invalid_input_raises_422_before_authorize() -> None:
    with pytest.raises(ValidationException):
        StorePost.authorized({})  # missing title


class _JsonBody:
    """A minimal duck-typed litestar-request stand-in — just enough for ``Request.json()``."""

    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body

    async def json(self) -> dict[str, Any]:
        return self._body


async def test_request_validate_and_form_request_authorize_raise_the_same_type() -> None:
    """H15/DR-0040: both authorize-fail entry points raise AuthorizationException — not just
    "both 403", the identical type (a caller/test catching one type must catch both)."""
    with pytest.raises(AuthorizationException) as via_request:
        await Request(_JsonBody({"title": "forbidden"})).validate(StorePost)
    with pytest.raises(AuthorizationException) as via_form_request:
        StorePost.authorized({"title": "forbidden"})

    assert type(via_request.value) is AuthorizationException
    assert type(via_form_request.value) is AuthorizationException
    assert via_request.value.status == via_form_request.value.status == 403


# --- AR-004: authorize() runs before SEMANTIC rules() so a denied caller gets 403, not a 422 -----
# leaking the endpoint's rule contract. (Structural shape still precedes authorize — authorize reads
# a typed instance, and the structural schema is already public via OpenAPI; see DR-0072.)


class GuardedPost(FormRequest):
    title: str

    @classmethod
    def rules(cls) -> dict[str, Any]:
        return {"title": "min:5"}  # a SEMANTIC rule (not structural) — only rules() enforces it

    def authorize(self) -> bool:
        return False  # denied regardless of input (e.g. a non-admin caller)


def test_denied_caller_gets_403_not_a_422_leaking_the_rule_contract() -> None:
    # title is structurally valid (a str) but fails the semantic min:5 rule AND the caller is denied.
    # authorize() must win → 403, without ever surfacing the rule's 422 message.
    with pytest.raises(AuthorizationException) as exc:
        GuardedPost.authorized({"title": "ab"})
    assert exc.value.status == 403


async def test_request_validate_denied_before_semantic_rules() -> None:
    with pytest.raises(AuthorizationException) as exc:
        await Request(_JsonBody({"title": "ab"})).validate(GuardedPost)
    assert exc.value.status == 403


def test_structurally_invalid_still_422_before_authorize() -> None:
    # structural failure still precedes authorize (authorize needs a typed instance; structural
    # shape is public) — the deliberate, documented residual.
    with pytest.raises(ValidationException):
        GuardedPost.authorized({})  # missing title entirely → msgspec structural 422
