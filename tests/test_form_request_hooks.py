"""Validation — FormRequest lifecycle hooks that map cleanly onto the msgspec path:
``prepare_for_validation`` (normalize input before convert) and ``passed_validation``
(post-success transform).

``with_validator`` is intentionally NOT on the msgspec FormRequest — it belongs to the rule
``Validator`` (see note in validation/__init__.py)."""

from __future__ import annotations

from typing import Any

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
