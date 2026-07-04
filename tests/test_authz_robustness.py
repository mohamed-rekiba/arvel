"""Sudo-confirm throttling + Authorize ability boot-assertion."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.auth import Gate, current_user
from arvel.auth.confirm import confirm_password
from arvel.auth.middleware import Authorize, Middleware, assert_abilities_defined
from arvel.security import Hasher
from arvel.support.facades import Log


class _User:
    id = 1

    def get_auth_identifier(self) -> int:
        return self.id

    def get_auth_password(self) -> str:
        return Hasher().make("secret")


class _Req:
    def __init__(self) -> None:
        self.session: dict[str, Any] = {}


class _FakeLimiter:
    def __init__(self, locked: bool = False) -> None:
        self.locked = locked
        self.failures: list[str] = []
        self.cleared: list[str] = []

    async def too_many_attempts(self, key: str) -> bool:
        return self.locked

    async def record_failure(self, key: str) -> int:
        self.failures.append(key)
        return len(self.failures)

    async def clear(self, key: str) -> None:
        self.cleared.append(key)


class _CapLog:
    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict[str, Any]]] = []
        self._ch: str | None = None

    def channel(self, name: str) -> _CapLog:
        self._ch = name
        return self

    def info(self, event: str, **f: Any) -> None:
        self.records.append(("info", event, f))

    def warning(self, event: str, **f: Any) -> None:
        self.records.append(("warning", event, f))


# --- sudo-confirm throttling -----------------------------------------------------


async def test_confirm_wrong_password_records_failure_and_audits() -> None:
    limiter = _FakeLimiter()
    log = _CapLog()
    Log.swap(log)
    token = current_user.set(_User())
    try:
        assert await confirm_password(_Req(), "WRONG", limiter=limiter) is False
        assert limiter.failures == ["1"]  # counted against the user id
    finally:
        current_user.reset(token)
        Log.clear_swapped()
    assert any(
        e == "auth.password_confirm.failed" and lvl == "warning" for lvl, e, _ in log.records
    )


async def test_confirm_locked_fails_fast_without_checking_password() -> None:
    limiter = _FakeLimiter(locked=True)
    log = _CapLog()
    Log.swap(log)
    token = current_user.set(_User())
    try:
        assert (
            await confirm_password(_Req(), "secret", limiter=limiter) is False
        )  # right pw, but locked
        assert limiter.failures == []  # never reached the password check
    finally:
        current_user.reset(token)
        Log.clear_swapped()
    assert any(e == "auth.password_confirm.locked" for _l, e, _ in log.records)


async def test_confirm_success_clears_the_limiter() -> None:
    limiter = _FakeLimiter()
    token = current_user.set(_User())
    try:
        req = _Req()
        assert await confirm_password(req, "secret", limiter=limiter) is True
        assert limiter.cleared == ["1"] and limiter.failures == []
        assert "_password_confirmed_at" in req.session
    finally:
        current_user.reset(token)


async def test_confirm_without_limiter_unchanged() -> None:
    token = current_user.set(_User())
    try:
        assert await confirm_password(_Req(), "secret") is True
        assert await confirm_password(_Req(), "nope") is False
    finally:
        current_user.reset(token)


# --- Authorize ability boot-assertion --------------------------------------------


def test_authorize_exposes_required_ability() -> None:
    assert Authorize("posts.publish").required_ability == "posts.publish"


def test_assert_abilities_defined_passes_for_defined() -> None:
    gate = Gate()
    gate.define("posts.publish", lambda user: True)

    class Plain(Middleware):  # non-Authorize middleware is ignored
        pass

    assert_abilities_defined(gate, [Authorize("posts.publish"), Plain])  # no raise


def test_assert_abilities_defined_raises_for_typo() -> None:
    gate = Gate()
    gate.define("posts.publish", lambda user: True)
    with pytest.raises(ValueError, match=r"posts\.typo"):
        assert_abilities_defined(gate, [Authorize("posts.publish"), Authorize("posts.typo")])
