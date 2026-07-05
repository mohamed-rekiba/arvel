"""arvel.http.middleware — the form ``_method`` override helpers (``_multipart_field`` /
``_form_method_override``) that spoof PUT/PATCH/DELETE from an HTML form body."""

from __future__ import annotations

from arvel.http.middleware import (
    _form_method_override,  # pyright: ignore[reportPrivateUsage]
    _multipart_field,  # pyright: ignore[reportPrivateUsage]
)


def _multipart(boundary: str, field: str, value: str) -> tuple[str, bytes]:
    ctype = f"multipart/form-data; boundary={boundary}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"\r\n\r\n'
        f"{value}\r\n"
        f"--{boundary}--\r\n"
    ).encode("latin-1")
    return ctype, body


def test_multipart_field_extracts_value() -> None:
    ctype, body = _multipart("X123", "_method", "PUT")
    assert _multipart_field(ctype, body, "_method") == "PUT"


def test_multipart_field_missing_boundary_or_field() -> None:
    assert _multipart_field("multipart/form-data", b"", "_method") == ""  # no boundary=
    ctype, body = _multipart("X123", "other", "PUT")
    assert _multipart_field(ctype, body, "_method") == ""  # field absent


def test_form_method_override_urlencoded_multipart_and_other() -> None:
    assert _form_method_override("application/x-www-form-urlencoded", b"_method=patch") == "PATCH"
    ctype, body = _multipart("B", "_method", "delete")
    assert _form_method_override(ctype, body) == "DELETE"
    assert _form_method_override("application/json", b"{}") == ""  # unhandled content type
