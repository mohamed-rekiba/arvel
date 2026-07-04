"""old-input — a validation failure flashes submitted input for one request via ``old()``, excluding
password fields (Laravel dontFlash)."""

from __future__ import annotations

from typing import Any

import msgspec
import pytest

from arvel.http.flash import FlashBag


def test_flash_input_and_old_readback() -> None:
    session: dict[str, Any] = {}
    FlashBag(session).flash_input({"email": "a@b.com", "name": "Ada"})
    bag = FlashBag(session)
    assert bag.old("email") == "a@b.com"
    assert bag.old("missing", "default") == "default"
    assert bag.old() == {"email": "a@b.com", "name": "Ada"}  # all input


def test_old_is_empty_without_flashed_input() -> None:
    bag = FlashBag({})
    assert bag.old() == {}
    assert bag.old("anything") is None


def test_old_input_ages_out_after_one_request() -> None:
    session: dict[str, Any] = {}
    FlashBag(session).flash_input({"email": "a@b.com"})
    FlashBag(session).age()  # request B: still fresh → kept
    assert FlashBag(session).old("email") == "a@b.com"
    FlashBag(session).age()  # request C: aged out
    assert FlashBag(session).old("email") is None


class _LoginForm(msgspec.Struct):
    email: str
    age: int  # required → a payload without it fails validation


class _FakeLitestar:
    """Minimal litestar-request stand-in: arvel Request.json() calls ``self._r.json()``."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    async def json(self) -> Any:
        return self._payload


def _request(payload: dict[str, Any], session: dict[str, Any] | None) -> Any:
    from arvel.http.request import Request

    req = Request(_FakeLitestar(payload))  # the real arvel Request, real validate()/old-input path
    if session is not None:
        req.session = session  # StartSession sets this on the web group
    return req


async def test_validate_failure_flashes_input_minus_passwords() -> None:
    from arvel.validation import ValidationException

    session: dict[str, Any] = {}
    req = _request({"email": "not-an-email", "password": "secret123"}, session)  # missing `age`
    with pytest.raises(ValidationException):
        await req.validate(_LoginForm)
    flashed = FlashBag(session).old()
    assert flashed.get("email") == "not-an-email"  # input repopulated for the redirected-back form
    assert "password" not in flashed  # password NEVER flashed (Laravel dontFlash)


async def test_validate_failure_without_session_is_safe() -> None:
    from arvel.validation import ValidationException

    req = _request({"email": "bad"}, session=None)  # api group: no .session attribute
    with pytest.raises(ValidationException):
        await req.validate(_LoginForm)
    # must not raise AttributeError for the missing session — old-input is a no-op off the web group
