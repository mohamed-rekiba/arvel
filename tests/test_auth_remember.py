"""Persistent login ("remember me"), selector/validator pattern."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from arvel.auth import current_user
from arvel.auth.remember import (
    REMEMBER_COOKIE,
    RememberMe,
    RememberToken,
    clear_all_remember_tokens,
    clear_remember_token,
    forget_remember,
    issue_remember_token,
    recall_remember_token,
    remember,
)
from arvel.database import ConnectionResolver


async def _db() -> ConnectionResolver:
    db = ConnectionResolver()
    RememberToken.set_connection(db)
    await db.execute(sa.schema.CreateTable(RememberToken.__table__))
    return db


class FakeUser:
    def __init__(self, uid: int) -> None:
        self.id = uid

    def get_auth_identifier(self) -> int:
        return self.id


class FakeRequest:
    def __init__(self, cookies: dict[str, str] | None = None, session: Any = None) -> None:
        self._cookies = cookies or {}
        self.session = session

    def cookie(self, name: str, default: str | None = None) -> str | None:
        return self._cookies.get(name, default)


class FakeResponse:
    def __init__(self) -> None:
        self.set: list[tuple[str, str, dict[str, Any]]] = []
        self.deleted: list[tuple[str, dict[str, Any]]] = []

    def set_cookie(self, key: str, value: str, **kw: Any) -> None:
        self.set.append((key, value, kw))

    def delete_cookie(self, key: str, **kw: Any) -> None:
        self.deleted.append((key, kw))


# --- token store: issue / recall / rotate / theft -----------------------------


async def test_issue_recall_rotates_and_detects_reuse() -> None:
    db = await _db()
    try:
        cookie = await issue_remember_token(42)

        r1 = await recall_remember_token(cookie)
        assert r1 is not None and r1[0] == 42
        rotated1 = r1[1]
        assert rotated1 != cookie  # validator rotated (single-use)

        r2 = await recall_remember_token(rotated1)  # legitimate continued use
        assert r2 is not None and r2[0] == 42
        rotated2 = r2[1]
        assert rotated2 != rotated1

        # replaying the ORIGINAL (now-stale) cookie is a theft signal → token destroyed
        assert await recall_remember_token(cookie) is None
        assert await recall_remember_token(rotated2) is None  # whole token killed
    finally:
        await db.dispose()


async def test_unknown_and_malformed_cookies_rejected() -> None:
    db = await _db()
    try:
        assert await recall_remember_token("nope:whatever") is None
        assert await recall_remember_token("no-colon") is None
        assert await recall_remember_token("") is None
        assert await recall_remember_token(":") is None
    finally:
        await db.dispose()


async def test_forged_validator_rejected_and_token_deleted() -> None:
    db = await _db()
    try:
        cookie = await issue_remember_token(7)
        selector = cookie.split(":")[0]
        assert await recall_remember_token(f"{selector}:forged-validator") is None
        # the forged attempt deleted the row → even the real cookie no longer works
        assert await recall_remember_token(cookie) is None
    finally:
        await db.dispose()


async def test_expired_token_rejected() -> None:
    db = await _db()
    try:
        cookie = await issue_remember_token(7, ttl=-10)  # already expired
        assert await recall_remember_token(cookie) is None
    finally:
        await db.dispose()


async def test_clear_and_clear_all() -> None:
    db = await _db()
    try:
        c1 = await issue_remember_token(5)
        await clear_remember_token(c1)
        assert await recall_remember_token(c1) is None

        a = await issue_remember_token(9)
        b = await issue_remember_token(9)
        await clear_all_remember_tokens(9)
        assert await recall_remember_token(a) is None
        assert await recall_remember_token(b) is None
    finally:
        await db.dispose()


# --- HTTP glue: middleware + login/logout helpers -----------------------------


async def test_middleware_recalls_logged_out_user() -> None:
    db = await _db()
    try:
        cookie = await issue_remember_token(42)
        req = FakeRequest(cookies={REMEMBER_COOKIE: cookie}, session={})
        req._session_id = "pre-auth-sid"  # as StartSession would have set it
        seen: dict[str, Any] = {}

        async def dest(_r: Any) -> str:
            seen["user"] = current_user.get()
            return "ok"

        mw = RememberMe(lambda uid: FakeUser(uid), secure=False)
        assert await mw.handle(req, dest) == "ok"
        assert isinstance(seen["user"], FakeUser) and seen["user"].id == 42  # logged in
        assert current_user.get() is None  # reset after request
        assert req.session["_user_id"] == 42  # session seeded
        assert req._session_id != "pre-auth-sid"  # session id rotated (fixation)
        assert req._remember_set and req._remember_set != cookie  # rotated cookie flagged

        resp = FakeResponse()
        await mw.terminate(req, resp)
        key, value, kw = resp.set[0]
        assert key == REMEMBER_COOKIE and value == req._remember_set
        assert kw["httponly"] and kw["samesite"] == "lax" and kw["secure"] is False
        assert kw["max_age"] > 0
    finally:
        await db.dispose()


async def test_middleware_passes_through_when_already_authenticated() -> None:
    db = await _db()
    try:
        cookie = await issue_remember_token(42)
        req = FakeRequest(cookies={REMEMBER_COOKIE: cookie})
        token = current_user.set(FakeUser(99))  # already logged in via session
        try:
            mw = RememberMe(lambda uid: FakeUser(uid))
            await mw.handle(req, lambda _r: _ok())
        finally:
            current_user.reset(token)
        assert not hasattr(req, "_remember_set")  # no recall happened
        # the remember token is untouched (not rotated)
        assert await recall_remember_token(cookie) is not None
    finally:
        await db.dispose()


async def test_middleware_clears_invalid_cookie() -> None:
    db = await _db()
    try:
        req = FakeRequest(cookies={REMEMBER_COOKIE: "bad:cookie"})
        mw = RememberMe(lambda uid: FakeUser(uid))
        await mw.handle(req, lambda _r: _ok())
        assert req._remember_clear is True
        resp = FakeResponse()
        await mw.terminate(req, resp)
        assert resp.deleted and resp.deleted[0][0] == REMEMBER_COOKIE
        assert resp.set == []
    finally:
        await db.dispose()


async def test_remember_and_forget_helpers() -> None:
    db = await _db()
    try:
        req = FakeRequest()
        await remember(req, FakeUser(42))
        assert req._remember_set  # cookie flagged
        recalled = await recall_remember_token(req._remember_set)
        assert recalled is not None and recalled[0] == 42  # a real token was issued

        # logout: cookie present → forget clears it
        req2 = FakeRequest(cookies={REMEMBER_COOKIE: req._remember_set})
        await forget_remember(req2)
        assert req2._remember_clear is True
        assert await recall_remember_token(req._remember_set) is None
    finally:
        await db.dispose()


async def _ok() -> str:
    return "ok"
