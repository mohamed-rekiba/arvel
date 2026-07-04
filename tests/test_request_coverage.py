"""Coverage — the Request wrapper over a Litestar request (doc 04)."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.http.request import Request


class _Url:
    path = "/users/5"


class FakeRequest:
    method = "POST"
    url = _Url()
    headers = {"x-test": "1"}
    query_params = {"q": "v"}
    path_params = {"id": "5"}

    async def json(self) -> dict[str, Any]:
        return {"a": 1}

    async def form(self) -> dict[str, Any]:
        return {"avatar": "file-object"}


def test_request_accessors() -> None:
    request = Request(FakeRequest())
    assert request.raw.__class__ is FakeRequest
    assert request.method() == "POST"
    assert request.path() == "/users/5"
    assert request.header("x-test") == "1"
    assert request.header("missing", "default") == "default"
    assert request.query("q") == "v"
    assert request.path_param("id") == "5"
    assert request.user() is None  # no auth bound
    assert request.is_("users/*")
    assert not request.is_("posts/*")


async def test_request_json_and_files() -> None:
    from arvel.http import UploadedFile

    request = Request(FakeRequest())
    assert await request.json() == {"a": 1}
    assert await request.form() == {"avatar": "file-object"}
    assert isinstance(await request.file("avatar"), UploadedFile)  # wrapped for .store()
    assert await request.file("missing", "fallback") == "fallback"  # absent → default


class _EmptyBody(FakeRequest):
    async def json(self) -> Any:  # litestar returns None for a request with no body
        return None


async def test_request_json_empty_body_returns_empty_dict() -> None:
    # Request.json() defaults to {} so `(...).get(x)` doesn't crash with "'NoneType' has no attribute 'get'"
    body = await Request(_EmptyBody()).json()
    assert body == {}
    assert body.get("email") is None  # no AttributeError


async def test_request_validate_empty_body_raises_clean_validation_error() -> None:
    import msgspec

    from arvel.validation import ValidationException

    class LoginIn(msgspec.Struct):
        email: str

    # an empty body → {} → validate reports the missing field (422), not a None/dict() crash (500)
    with pytest.raises(ValidationException):
        await Request(_EmptyBody()).validate(LoginIn)
