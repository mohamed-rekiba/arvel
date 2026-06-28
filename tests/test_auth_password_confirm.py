"""Auth (G6 hardening) — password confirmation / sudo mode."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.auth import current_user
from arvel.auth.confirm import (
    DEFAULT_WINDOW,
    EnsurePasswordConfirmed,
    confirm_password,
    password_confirmed,
)
from arvel.dates import Date
from arvel.http.exceptions import HttpException
from arvel.security import Hasher


class _User:
    def __init__(self, password: str, uid: int = 1) -> None:
        self.id = uid
        self.password = password

    def get_auth_password(self) -> str:
        return self.password


class _Req:
    """A request double with a mutable session dict (as StartSession provides)."""

    def __init__(self, session: dict[str, Any] | None = None) -> None:
        self.session = session if session is not None else {}


async def _ok(_req: Any) -> str:
    return "OK"


# --- confirm_password ---------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_with_correct_password() -> None:
    token = current_user.set(_User(Hasher().make("secret")))
    try:
        req = _Req()
        assert await confirm_password(req, "secret") is True
        assert "_password_confirmed_at" in req.session
    finally:
        current_user.reset(token)


@pytest.mark.asyncio
async def test_confirm_with_wrong_password() -> None:
    token = current_user.set(_User(Hasher().make("secret")))
    try:
        req = _Req()
        assert await confirm_password(req, "WRONG") is False
        assert "_password_confirmed_at" not in req.session
    finally:
        current_user.reset(token)


@pytest.mark.asyncio
async def test_confirm_requires_a_user_and_session() -> None:
    token = current_user.set(None)
    try:
        assert await confirm_password(_Req(), "secret") is False  # guest
    finally:
        current_user.reset(token)


# --- password_confirmed freshness (clock via Date.set_test_now) ---------------


def test_unconfirmed_session_is_not_confirmed() -> None:
    assert password_confirmed(_Req()) is False
    assert password_confirmed(_Req(session={})) is False


@pytest.mark.asyncio
async def test_confirmation_expires_after_the_window() -> None:
    base = Date.now()
    Date.set_test_now(base)
    token = current_user.set(_User(Hasher().make("secret")))
    try:
        req = _Req()
        await confirm_password(req, "secret")
        assert password_confirmed(req, within=300) is True  # just confirmed

        Date.set_test_now(base.add(seconds=240))
        assert password_confirmed(req, within=300) is True  # still fresh
        Date.set_test_now(base.add(seconds=360))
        assert password_confirmed(req, within=300) is False  # expired
    finally:
        current_user.reset(token)
        Date.set_test_now(None)


def test_default_window_is_three_hours() -> None:
    assert DEFAULT_WINDOW == 10800


# --- EnsurePasswordConfirmed middleware ---------------------------------------


@pytest.mark.asyncio
async def test_middleware_blocks_when_unconfirmed() -> None:
    with pytest.raises(HttpException) as exc:
        await EnsurePasswordConfirmed().handle(_Req(), _ok)
    assert exc.value.status == 403


@pytest.mark.asyncio
async def test_middleware_passes_when_freshly_confirmed() -> None:
    token = current_user.set(_User(Hasher().make("secret")))
    try:
        req = _Req()
        await confirm_password(req, "secret")
        assert await EnsurePasswordConfirmed().handle(req, _ok) == "OK"
    finally:
        current_user.reset(token)


# --- security regressions (from the G6 review) --------------------------------


@pytest.mark.asyncio
async def test_confirmation_is_bound_to_the_user_no_cross_user_inheritance() -> None:
    """A confirmation must not carry over to a DIFFERENT user on the same session (CRITICAL fix)."""
    req = _Req()
    alice = current_user.set(_User(Hasher().make("secret"), uid=1))
    try:
        await confirm_password(req, "secret")
        assert password_confirmed(req) is True
    finally:
        current_user.reset(alice)

    bob = current_user.set(_User(Hasher().make("other"), uid=2))  # different user, same session
    try:
        assert password_confirmed(req) is False  # Bob did NOT inherit Alice's grant
        with pytest.raises(HttpException) as exc:
            await EnsurePasswordConfirmed().handle(req, _ok)
        assert exc.value.status == 403
    finally:
        current_user.reset(bob)


@pytest.mark.asyncio
async def test_malformed_stored_hash_fails_closed() -> None:
    """A non-verifiable stored hash must return False, not raise (MEDIUM fix)."""
    token = current_user.set(_User("not-a-valid-argon2-hash"))
    try:
        assert await confirm_password(_Req(), "secret") is False
    finally:
        current_user.reset(token)
