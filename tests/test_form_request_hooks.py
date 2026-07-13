"""Validation — FormRequest lifecycle hooks that map cleanly onto the msgspec path:
``prepare_for_validation`` (normalize input before convert) and ``passed_validation``
(post-success transform).

``with_validator`` is intentionally NOT on the msgspec FormRequest — it belongs to the rule
``Validator`` (see note in validation/__init__.py)."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.validation import FormRequest


class CreatePost(FormRequest):
    title: str
    slug: str

    @classmethod
    def prepare_for_validation(cls, data: dict[str, Any]) -> dict[str, Any]:
        # derive slug from title when the client didn't send one
        if not data.get("slug") and data.get("title"):
            data["slug"] = str(data["title"]).lower().replace(" ", "-")
        return data

    def passed_validation(self) -> None:
        self.title = self.title.strip()


def test_prepare_for_validation_fills_missing_field() -> None:
    post = CreatePost.parse({"title": "Hello World"})
    assert post.slug == "hello-world"


def test_prepare_for_validation_respects_provided_value() -> None:
    post = CreatePost.parse({"title": "Hello World", "slug": "custom"})
    assert post.slug == "custom"


def test_passed_validation_runs_after_success() -> None:
    post = CreatePost.parse({"title": "  spaced  ", "slug": "s"})
    assert post.title == "spaced"  # passed_validation stripped it


def test_default_hooks_are_noops() -> None:
    class Plain(FormRequest):
        name: str

    p = Plain.parse({"name": "x"})
    assert p.name == "x"


# --- the same lifecycle must run when the FormRequest goes through Request.validate, not just
#     through parse() directly. -----------------------------------------------------------------


class _Body:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    async def json(self) -> Any:
        return self._data


class Signup(FormRequest):
    email: str
    slug: str

    @classmethod
    def prepare_for_validation(cls, data: dict[str, Any]) -> dict[str, Any]:
        data.setdefault("slug", "auto")  # a required field the client omits
        return data

    def passed_validation(self) -> None:
        self.email = self.email.lower()

    @classmethod
    def rules(cls) -> dict[str, str | list[Any]]:
        return {"email": "string|min:6"}  # a semantic check msgspec can't express


async def test_request_validate_runs_the_full_form_request_lifecycle() -> None:
    from arvel.http.request import Request

    # slug is required but omitted — only prepare_for_validation filling it keeps msgspec happy
    dto = await Request(_Body({"email": "ME@X.com"})).validate(Signup)
    assert dto.slug == "auto"  # prepare_for_validation ran
    assert dto.email == "me@x.com"  # passed_validation ran


async def test_request_validate_enforces_form_request_rules() -> None:
    from arvel.http.request import Request
    from arvel.validation import ValidationException

    # "a@b.c" is a valid str (msgspec passes) but 5 chars — fails rules() string|min:6
    with pytest.raises(ValidationException):
        await Request(_Body({"email": "a@b.c", "slug": "x"})).validate(Signup)
