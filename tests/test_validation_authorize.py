"""Validation (doc 10) — FormRequest authorize() -> 403 enforcement."""

from __future__ import annotations

import pytest

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
