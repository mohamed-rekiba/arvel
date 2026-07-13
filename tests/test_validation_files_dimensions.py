"""Spec 12 §2 — file rules: `mimetypes`, `extensions` (metadata-only, mirrors `mimes`), and
`dimensions` (reads real pixel data via Pillow — the `image` extra, already installed here for
`arvel.media`; a missing extra is an honest `MissingExtraError`, not a silent pass — see
test_validation_strict.py's sibling module for that failure-mode contract)."""

from __future__ import annotations

import io

from PIL import Image

from arvel.validation import Validator


class Upload:
    """Duck-typed upload stand-in (matches tests/test_validator_files.py's `Upload`)."""

    def __init__(self, filename: str, content_type: str) -> None:
        self.filename = filename
        self.content_type = content_type


def _png_bytes(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height)).save(buf, format="PNG")
    return buf.getvalue()


def test_mimetypes_rule() -> None:
    ok = Validator({"f": Upload("a.png", "image/png")}, {"f": "mimetypes:image/png,image/jpeg"})
    assert ok.passes()
    bad = Validator({"f": Upload("a.gif", "image/gif")}, {"f": "mimetypes:image/png,image/jpeg"})
    assert bad.fails()


def test_extensions_rule() -> None:
    ok = Validator({"f": Upload("photo.JPG", "image/jpeg")}, {"f": "extensions:png,jpg"})
    assert ok.passes()  # case-insensitive, like `mimes`
    bad = Validator({"f": Upload("a.gif", "image/gif")}, {"f": "extensions:png,jpg"})
    assert bad.fails()


def test_dimensions_rule_on_raw_bytes() -> None:
    raw = _png_bytes(100, 50)
    ok = Validator({"img": raw}, {"img": "dimensions:min_width=50,min_height=20"})
    assert ok.passes()
    bad = Validator({"img": raw}, {"img": "dimensions:min_width=200"})
    assert bad.fails()


def test_dimensions_rule_exact_and_ratio() -> None:
    raw = _png_bytes(100, 50)
    assert Validator({"img": raw}, {"img": "dimensions:width=100,height=50"}).passes()
    assert Validator({"img": raw}, {"img": "dimensions:width=99"}).fails()
    assert Validator({"img": raw}, {"img": "dimensions:ratio=2/1"}).passes()
    assert Validator({"img": raw}, {"img": "dimensions:ratio=1/1"}).fails()


def test_dimensions_rule_fails_on_garbage_bytes() -> None:
    assert Validator({"img": b"not-an-image"}, {"img": "dimensions:min_width=1"}).fails()
