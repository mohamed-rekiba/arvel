"""CSRF parity — fixes a real green-but-broken bug: the session ``_token`` was NEVER seeded,
so every web-group POST got a 419 (and there was no way to obtain a token). ValidateCsrfToken now seeds
the token, accepts it from the ``_token`` form/JSON field or the X-CSRF-TOKEN / X-XSRF-TOKEN header, and
the view exposes csrf_token()/csrf_field()."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.http.middleware import ValidateCsrfToken
from arvel.http.request import current_request
from arvel.validation import ValidationException
from arvel.views import ViewFactory, _csrf_field, _csrf_token

_FORM_CT = {"content-type": "application/x-www-form-urlencoded"}


class _Req:
    def __init__(
        self,
        method: str,
        session: dict[str, Any],
        header: dict[str, str] | None = None,
        form: dict[str, Any] | None = None,
    ) -> None:
        self._m = method
        self.session = session
        self._h = header or {}
        self._form = form or {}

    def method(self) -> str:
        return self._m

    def header(self, name: str, default: str | None = None) -> str | None:
        return self._h.get(name.lower(), default)

    async def form(self) -> Any:
        return self._form

    async def json(self) -> Any:
        return {}


async def _ran(_request: Any) -> str:
    return "HANDLER_RAN"


async def test_get_seeds_token_and_is_exempt() -> None:
    mw = ValidateCsrfToken()
    session: dict[str, Any] = {}
    assert await mw.handle(_Req("GET", session), _ran) == "HANDLER_RAN"
    assert isinstance(session["_token"], str) and len(session["_token"]) == 64


async def test_post_accepts_form_field_and_headers() -> None:
    mw = ValidateCsrfToken()
    session: dict[str, Any] = {}
    await mw.handle(_Req("GET", session), _ran)
    token = session["_token"]
    assert (
        await mw.handle(_Req("POST", session, _FORM_CT, {"_token": token}), _ran) == "HANDLER_RAN"
    )
    assert await mw.handle(_Req("POST", session, {"x-csrf-token": token}), _ran) == "HANDLER_RAN"
    assert await mw.handle(_Req("POST", session, {"x-xsrf-token": token}), _ran) == "HANDLER_RAN"


class _Resp:
    def __init__(self) -> None:
        self.cookies: list[tuple[str, str, dict[str, Any]]] = []

    def set_cookie(self, name: str, value: str, **kw: Any) -> None:
        self.cookies.append((name, value, kw))


async def test_terminate_sets_readable_xsrf_cookie() -> None:
    """Decoupled-SPA flow: the token is mirrored into a JS-readable XSRF-TOKEN cookie (Sanctum)."""
    mw = ValidateCsrfToken()
    session: dict[str, Any] = {}
    await mw.handle(_Req("GET", session), _ran)  # seeds session["_token"]
    response = _Resp()
    await mw.terminate(_Req("GET", session), response)
    name, value, kw = response.cookies[0]
    assert name == "XSRF-TOKEN"
    assert value == session["_token"]  # echoes the session token
    assert kw["httponly"] is False  # JS must be able to read it (not a secret)


async def test_post_rejects_missing_or_wrong_token() -> None:
    mw = ValidateCsrfToken()
    session: dict[str, Any] = {}
    await mw.handle(_Req("GET", session), _ran)
    with pytest.raises(ValidationException) as a:
        await mw.handle(_Req("POST", session, _FORM_CT, {}), _ran)
    assert a.value.status == 419
    with pytest.raises(ValidationException) as b:
        await mw.handle(_Req("POST", session, _FORM_CT, {"_token": "wrong"}), _ran)
    assert b.value.status == 419


def test_view_csrf_globals_registered() -> None:
    env = ViewFactory("resources/views").env
    assert "csrf_token" in env.globals
    assert "csrf_field" in env.globals


def test_csrf_token_and_field_read_the_request_session() -> None:
    token_ctx = current_request.set(_Req("GET", {"_token": "abc123"}))
    try:
        assert _csrf_token() == "abc123"
        assert str(_csrf_field()) == '<input type="hidden" name="_token" value="abc123">'
    finally:
        current_request.reset(token_ctx)


def test_csrf_token_degrades_without_request() -> None:
    token_ctx = current_request.set(None)
    try:
        assert _csrf_token() == ""
    finally:
        current_request.reset(token_ctx)
