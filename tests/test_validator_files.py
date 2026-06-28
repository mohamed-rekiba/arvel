"""Validation (doc 10) — file/image/mimes rules over uploaded files. Test-first."""

from __future__ import annotations

from arvel.validation import Validator


class Upload:
    """A stand-in for an uploaded file (duck-typed: filename + content_type)."""

    def __init__(self, filename: str, content_type: str) -> None:
        self.filename = filename
        self.content_type = content_type


def test_file_rule() -> None:
    assert Validator({"doc": Upload("a.pdf", "application/pdf")}, {"doc": "file"}).passes()
    assert Validator({"doc": "not-a-file"}, {"doc": "file"}).fails()


def test_image_rule() -> None:
    assert Validator({"avatar": Upload("a.png", "image/png")}, {"avatar": "image"}).passes()
    assert Validator({"avatar": Upload("a.pdf", "application/pdf")}, {"avatar": "image"}).fails()


def test_mimes_rule() -> None:
    ok = Validator({"avatar": Upload("a.png", "image/png")}, {"avatar": "mimes:png,jpg"})
    assert ok.passes()
    bad = Validator({"avatar": Upload("a.gif", "image/gif")}, {"avatar": "mimes:png,jpg"})
    assert bad.fails()


def test_combined_image_upload_rules() -> None:
    v = Validator(
        {"avatar": Upload("photo.JPG", "image/jpeg")},
        {"avatar": "required|image|mimes:png,jpg"},
    )
    assert v.passes()  # case-insensitive extension


def test_file_rule_message() -> None:
    v = Validator({"doc": 123}, {"doc": "file"})
    v.passes()
    assert "file" in v.errors()["doc"][0].lower()
