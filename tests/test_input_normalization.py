"""Global input normalization (H8): TrimStrings + ConvertEmptyStringsToNull.

Unit-level tests exercise each middleware's transform directly; the acceptance test drives the
real kernel (``use_default_global``) + ``TestClient`` + ``FormRequest`` validation — the actual
production path (``Request.validate`` -> ``json()`` -> the wired transforms), not a shortcut
around it."""

from __future__ import annotations

from typing import Any

from litestar.testing import TestClient

from arvel.http import HttpKernel
from arvel.http.middleware import ConvertEmptyStringsToNull, TrimStrings
from arvel.http.request import Request
from arvel.validation import FormRequest

# --- TrimStrings ---------------------------------------------------------------------------


def test_trim_strings_strips_leading_and_trailing_whitespace() -> None:
    mw = TrimStrings()
    assert mw._transform("  hi  ") == "hi"
    assert mw._transform(5) == 5  # non-strings pass through untouched


def test_trim_strings_recurses_through_nested_dicts_and_lists() -> None:
    mw = TrimStrings()
    out = mw._transform({"a": " x ", "b": [" y ", {"c": " z "}]})
    assert out == {"a": "x", "b": ["y", {"c": "z"}]}


def test_trim_strings_skips_except_keys_at_any_depth() -> None:
    mw = TrimStrings()
    out = mw._transform({"password": "  secret  ", "nested": {"password_confirmation": "  s  "}})
    assert out == {"password": "  secret  ", "nested": {"password_confirmation": "  s  "}}


async def test_trim_strings_handle_appends_its_transform() -> None:
    class _Req:
        def __init__(self) -> None:
            self._input_transforms: list[Any] = []

    request = _Req()

    async def call_next(req: Any) -> str:
        return "ok"

    assert await TrimStrings().handle(request, call_next) == "ok"
    assert len(request._input_transforms) == 1
    assert request._input_transforms[0]("  x  ") == "x"  # the appended callable is the transform


# --- ConvertEmptyStringsToNull --------------------------------------------------------------


def test_convert_empty_strings_to_null() -> None:
    mw = ConvertEmptyStringsToNull()
    assert mw._transform("") is None
    assert mw._transform("kept") == "kept"
    assert mw._transform(0) == 0  # falsy-but-not-empty-string values are untouched


def test_convert_empty_strings_to_null_recurses() -> None:
    mw = ConvertEmptyStringsToNull()
    out = mw._transform({"a": "", "b": ["", "x", {"c": ""}]})
    assert out == {"a": None, "b": [None, "x", {"c": None}]}


# --- Request.json()/all() apply the wired transforms, in order, and cache -------------------


class _Raw:
    def __init__(self, body: Any) -> None:
        self._body = body
        self.calls = 0
        self.query_params: dict[str, str] = {}

    async def json(self) -> Any:
        self.calls += 1
        return self._body


async def test_request_json_applies_transforms_in_order_and_caches() -> None:
    raw = _Raw({"name": "  ada  ", "nick": ""})
    request = Request(raw)
    request._input_transforms = [TrimStrings()._transform, ConvertEmptyStringsToNull()._transform]
    data = await request.json()
    assert data == {"name": "ada", "nick": None}
    await request.json()
    assert raw.calls == 1  # cached — the underlying parse ran exactly once


async def test_request_all_applies_transforms_to_query_values_too() -> None:
    raw = _Raw({})
    raw.query_params = {"q": "  hat  "}
    request = Request(raw)
    request._input_transforms = [TrimStrings()._transform]
    assert (await request.all())["q"] == "hat"


async def test_input_and_all_agree_on_a_normalized_query_value() -> None:
    """input(key)'s fast path must go through the same transforms all()[key] does — a trimmed
    or emptied query value can never disagree between the two."""
    raw = _Raw({})
    raw.query_params = {"q": "  hat  ", "blank": ""}
    request = Request(raw)
    request._input_transforms = [TrimStrings()._transform, ConvertEmptyStringsToNull()._transform]
    all_data = await request.all()
    assert await request.input("q") == all_data["q"] == "hat"
    assert await request.input("blank") == all_data["blank"] is None


# --- acceptance: the real kernel + validate() sees normalized input -------------------------


class Register(FormRequest):
    name: str
    nick: str | None = None


class RegisterWithPassword(FormRequest):
    name: str
    password: str


async def _register(request: Any) -> dict[str, Any]:
    form = await request.validate(Register)
    return {"name": form.name, "nick": form.nick}


async def _register_with_password(request: Any) -> dict[str, Any]:
    form = await request.validate(RegisterWithPassword)
    return {"name": form.name, "password": form.password}


def _client() -> TestClient[Any]:
    kernel = HttpKernel().use_default_global()
    kernel.post("/register", _register)
    kernel.post("/register-pw", _register_with_password)
    return TestClient(kernel.build())


def test_trailing_whitespace_trims_and_empty_string_becomes_null_for_a_nullable_field() -> None:
    with _client() as client:
        response = client.post("/register", json={"name": "  ada  ", "nick": ""})
    assert response.status_code == 201
    assert response.json() == {"name": "ada", "nick": None}  # trimmed; nullable "" -> absent


def test_empty_string_on_a_required_field_now_fails_validation() -> None:
    with _client() as client:
        response = client.post(
            "/register", json={"name": "", "nick": "x"}, headers={"accept": "application/json"}
        )
    assert response.status_code == 422  # "" -> None, and `name` isn't nullable


def test_password_field_is_not_trimmed() -> None:
    with _client() as client:
        response = client.post("/register-pw", json={"name": "ada", "password": "  s3cret  "})
    assert response.status_code == 201
    assert response.json() == {"name": "ada", "password": "  s3cret  "}  # untouched


def test_deeply_nested_hostile_body_does_not_500() -> None:
    from arvel.http.middleware import ConvertEmptyStringsToNull, TrimStrings

    hostile: object = ""
    for _ in range(3000):
        hostile = [hostile]
    for mw in (TrimStrings(), ConvertEmptyStringsToNull()):
        mw._transform(hostile)  # deep subtree passes through untransformed, no RecursionError
