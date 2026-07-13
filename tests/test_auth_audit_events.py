"""Security-audit events emitted on the framework Log `security` channel."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from arvel.auth import Authenticatable, AuthManager
from arvel.auth.devices import logout_everywhere
from arvel.auth.refresh import RefreshToken, issue_refresh_token, rotate_refresh_token
from arvel.auth.remember import RememberToken, issue_remember_token, recall_remember_token
from arvel.auth.throttle import LoginRateLimiter
from arvel.cache import CacheManager
from arvel.database import ConnectionResolver, Model
from arvel.security import Hasher
from arvel.support.facades import Log


class _FakeLog:
    def __init__(self) -> None:
        self.records: list[tuple[str, str | None, str, dict[str, Any]]] = []
        self._ch: str | None = None

    def channel(self, name: str) -> _FakeLog:
        self._ch = name
        return self

    def info(self, event: str, **f: Any) -> None:
        self.records.append(("info", self._ch, event, f))

    def warning(self, event: str, **f: Any) -> None:
        self.records.append(("warning", self._ch, event, f))


def _events(log: _FakeLog) -> dict[str, tuple[str, str | None, dict[str, Any]]]:
    return {event: (lvl, ch, f) for lvl, ch, event, f in log.records}


class User(Model, Authenticatable):
    __fields__ = {"email": str, "password": str}
    __fillable__ = ["email"]


async def _db(*models: Any) -> ConnectionResolver:
    db = ConnectionResolver()
    for m in models:
        m.set_connection(db)
        await db.execute(sa.schema.CreateTable(m.__table__))
    return db


async def _provider(credentials: dict[str, Any]) -> Any:
    return await User.where(email=credentials["email"]).first()


# --- login (AuthManager.attempt) ----------------------------------------------


async def test_login_failed_and_succeeded_audited() -> None:
    db = await _db(User)
    log = _FakeLog()
    Log.swap(log)
    try:
        user = await User.create(email="ada@example.com")
        user.password = Hasher().make("secret")
        await user.save()
        assert (
            await AuthManager().attempt({"email": "ada@example.com", "password": "x"}, _provider)
            is False
        )
        assert (
            await AuthManager().attempt(
                {"email": "ada@example.com", "password": "secret"}, _provider
            )
            is True
        )
    finally:
        AuthManager().logout()
        Log.clear_swapped()
        await db.dispose()
    ev = _events(log)
    assert (
        ev["auth.login.failed"][0] == "warning"
        and ev["auth.login.failed"][2]["identifier"] == "ada@example.com"
    )
    assert ev["auth.login.succeeded"][0] == "info"
    assert "auth.login.succeeded" in ev and ev["auth.login.succeeded"][2]["user_id"] is not None
    assert all(ch == "security" for _lvl, ch, _e, _f in log.records)


# --- lockout (LoginRateLimiter) -----------------------------------------------


async def test_lockout_trip_audited_once() -> None:
    limiter = LoginRateLimiter(CacheManager().driver("array"), max_attempts=2, decay_seconds=60)
    log = _FakeLog()
    Log.swap(log)
    try:
        await limiter.record_failure("ada@example.com")  # count 1 — no event
        await limiter.record_failure("ada@example.com")  # count 2 == max → locked_out
        await limiter.record_failure("ada@example.com")  # count 3 — no duplicate event
    finally:
        Log.clear_swapped()
    locked = [r for r in log.records if r[2] == "auth.login.locked_out"]
    assert len(locked) == 1
    assert locked[0][0] == "warning" and locked[0][3]["identifier"] == "ada@example.com"


# --- refresh-token reuse ------------------------------------------------------


async def test_refresh_reuse_audited() -> None:
    db = await _db(RefreshToken)
    log = _FakeLog()
    Log.swap(log)
    try:
        t = await issue_refresh_token(42)
        await rotate_refresh_token(t)  # legit rotation
        assert await rotate_refresh_token(t) is None  # reuse → family revoked
    finally:
        Log.clear_swapped()
        await db.dispose()
    ev = _events(log)
    assert (
        ev["auth.refresh.reused"][0] == "warning"
        and ev["auth.refresh.reused"][2]["tokenable_id"] == 42
    )


# --- remember-me theft --------------------------------------------------------


async def test_remember_theft_audited() -> None:
    db = await _db(RememberToken)
    log = _FakeLog()
    Log.swap(log)
    try:
        cookie = await issue_remember_token(7)
        selector = cookie.split(":")[0]
        assert await recall_remember_token(f"{selector}:forged") is None
    finally:
        Log.clear_swapped()
        await db.dispose()
    ev = _events(log)
    assert ev["auth.remember.theft_detected"][0] == "warning"
    assert ev["auth.remember.theft_detected"][2]["tokenable_id"] == 7


# --- logout everywhere --------------------------------------------------------


class _U:
    id = 9

    def get_auth_identifier(self) -> int:
        return self.id


async def test_logout_everywhere_audited() -> None:
    db = await _db(RefreshToken, RememberToken)
    from arvel.auth.tokens import ApiToken

    ApiToken.set_connection(db)
    await db.execute(sa.schema.CreateTable(ApiToken.__table__))
    log = _FakeLog()
    Log.swap(log)
    try:
        await logout_everywhere(_U())
    finally:
        Log.clear_swapped()
        await db.dispose()
    ev = _events(log)
    assert ev["auth.logout_everywhere"][0] == "info"
    assert ev["auth.logout_everywhere"][2] == {"tokenable_id": 9, "failures": 0}


# --- fail-safe: no app / no logger ------------------------------------------


def test_audit_is_noop_without_a_logger() -> None:
    from arvel.auth.audit import audit

    audit("auth.test.event", level="warning", x=1)  # must not raise (no app, no swap)
