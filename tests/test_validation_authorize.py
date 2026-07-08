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
