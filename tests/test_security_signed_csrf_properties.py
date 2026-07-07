"""Security — abuse/property coverage for signed-URL and CSRF: a tampered signed URL must never
validate, and CSRF comparison must be constant-time and not crash on a hostile (non-ASCII) token."""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from arvel.http.exceptions import HttpException
from arvel.http.middleware import ValidateCsrfToken
from arvel.routing import Router

KEY = "test-secret-key"


def _router() -> Router:
    r = Router()
    r.get("/posts/{post}", lambda request, post: {}, name="posts.show")
    return r


# --- Signed URLs: no tamper ever validates --------------------------------------


@given(post=st.integers(min_value=0, max_value=10_000), index=st.integers(min_value=0))
@settings(max_examples=200)
def test_signed_url_path_tamper_never_validates(post: int, index: int) -> None:
    """Altering the protected path/query must never validate; re-encoding the signature
    token itself can be base64-redundant (harmless) — what matters is the signed resource can't change."""
    r = _router()
    signed = r.signed_url("posts.show", key=KEY, post=post)
    base, sep, token = signed.partition("?signature=")
    if not sep:
        return
    i = index % len(base)
    repl = "9" if base[i] != "9" else "8"
    tampered = base[:i] + repl + base[i + 1 :] + sep + token
    if tampered == signed:
        return
    assert r.has_valid_signature(tampered, key=KEY) is False


@given(post=st.integers(min_value=0, max_value=10_000))
@settings(max_examples=100)
def test_signed_url_wrong_key_never_validates(post: int) -> None:
    r = _router()
    signed = r.signed_url("posts.show", key=KEY, post=post)
    assert r.has_valid_signature(signed, key="another-key") is False


@given(garbage=st.text(max_size=80))
@settings(max_examples=200)
def test_signed_url_arbitrary_input_never_crashes(garbage: str) -> None:
    """Arbitrary attacker input to the verifier returns False, never raises."""
    r = _router()
    assert r.has_valid_signature(garbage, key=KEY) is False
    assert r.has_valid_signature(f"/posts/1?signature={garbage}", key=KEY) is False


# --- CSRF: constant-time + hostile-token safety ---------------------------------


class _Req:
    def __init__(self, method: str, sent: Any, session_token: str | None = "tok") -> None:
        self._method = method
        self._headers = {"x-csrf-token": sent}
        self.session: dict[str, Any] = {"_token": session_token} if session_token else {}

    def method(self) -> str:
        return self._method

    def header(self, name: str, default: Any = None) -> Any:
        return self._headers.get(name, default)


async def _ok(_request: Any) -> str:
    return "ok"


async def test_csrf_matching_token_passes() -> None:
    csrf = ValidateCsrfToken()
    assert await csrf.handle(_Req("POST", "tok", "tok"), _ok) == "ok"


async def test_csrf_non_ascii_token_is_rejected_cleanly() -> None:
    """A hostile non-ASCII header must yield a 419, not a 500 — secrets.compare_digest rejects non-ASCII str, so the impl must compare as bytes."""
    csrf = ValidateCsrfToken()
    with pytest.raises(HttpException) as exc:
        await csrf.handle(_Req("POST", "tökén", "tok"), _ok)
    assert exc.value.status == 419


@given(sent=st.text(min_size=1), expected=st.text(min_size=1))
@settings(max_examples=200)
async def test_csrf_only_exact_match_passes(sent: str, expected: str) -> None:
    csrf = ValidateCsrfToken()
    req = _Req("POST", sent, expected)
    if sent == expected:
        assert await csrf.handle(req, _ok) == "ok"
    else:
        with pytest.raises(HttpException):
            await csrf.handle(req, _ok)
