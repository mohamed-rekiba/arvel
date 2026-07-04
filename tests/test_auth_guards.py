"""Authentication guards: LocalGuard, SessionGuard, GuardManager, recast AuthManager.attempt.

LocalGuard is tested with an injected lookup (no DB); SessionGuard over the current_user ContextVar.
"""

from __future__ import annotations

from typing import Any

import pytest

from arvel.auth import Authenticatable, AuthManager, current_user
from arvel.auth.guards import GuardManager, LocalGuard, SessionGuard
from arvel.security import Hasher


def _lookup_for(stored: dict[str, str]) -> Any:
    async def _lookup(identifier: str) -> str | None:
        return stored.get(identifier)

    return _lookup


# --- LocalGuard ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_local_guard_attempt_success() -> None:
    hashed = Hasher().make("s3cret")
    guard = LocalGuard(_lookup_for({"ada": hashed}))

    principal = await guard.attempt("ada", "s3cret")
    assert principal is not None
    assert principal.provider == "local"
    assert principal.subject == "ada"


@pytest.mark.asyncio
async def test_local_guard_attempt_wrong_password() -> None:
    guard = LocalGuard(_lookup_for({"ada": Hasher().make("s3cret")}))
    assert await guard.attempt("ada", "wrong") is None


@pytest.mark.asyncio
async def test_local_guard_attempt_unknown_identifier() -> None:
    guard = LocalGuard(_lookup_for({}))
    assert await guard.attempt("nobody", "whatever") is None


@pytest.mark.asyncio
async def test_local_guard_verify_extracts_form() -> None:
    hashed = Hasher().make("pw")
    guard = LocalGuard(_lookup_for({"ada@corp.com": hashed}))

    class _Req:
        async def form(self) -> dict[str, str]:
            return {"email": "ada@corp.com", "password": "pw"}

    principal = await guard.verify(_Req())
    assert principal is not None
    assert principal.subject == "ada@corp.com"


@pytest.mark.asyncio
async def test_local_guard_verify_missing_fields_returns_none() -> None:
    guard = LocalGuard(_lookup_for({}))

    class _Req:
        async def form(self) -> dict[str, str]:
            return {}

    assert await guard.verify(_Req()) is None


# --- SessionGuard -------------------------------------------------------------


class _User(Authenticatable):
    def __init__(self, uid: int) -> None:
        self.id = uid


@pytest.mark.asyncio
async def test_session_guard_reflects_current_user() -> None:
    token = current_user.set(_User(7))
    try:
        principal = await SessionGuard().verify()
        assert principal is not None
        assert principal.provider == "session"
        assert principal.subject == "7"
    finally:
        current_user.reset(token)


@pytest.mark.asyncio
async def test_session_guard_none_when_guest() -> None:
    token = current_user.set(None)
    try:
        assert await SessionGuard().verify() is None
    finally:
        current_user.reset(token)


# --- SessionGuard.login / logout / user_id (14 AUTH-SESSION) ------------------


class _FakeSessionRequest:
    """A minimal request stand-in that plays along with ``StartSession``."""

    def __init__(self, cookies: dict[str, str] | None = None) -> None:
        self._cookies = cookies or {}
        self.session: dict[str, Any] = {}

    def cookie(self, name: str, default: str | None = None) -> str | None:
        return self._cookies.get(name, default)


@pytest.mark.asyncio
async def test_session_guard_login_regenerates_before_persisting_and_sets_current_user() -> None:
    from arvel.http.middleware import StartSession

    store: dict[str, dict[str, Any]] = {"attacker-fixed": {}}
    mw = StartSession(store=store, secure=False)
    req = _FakeSessionRequest({"session": "attacker-fixed"})
    seen: dict[str, Any] = {}

    async def dest(r: Any) -> str:
        await SessionGuard().login(_User(9), r)
        seen["user"] = current_user.get()
        return "ok"

    token = current_user.set(None)
    try:
        await mw.handle(req, dest)
    finally:
        current_user.reset(token)

    new_sid = req._session_id  # type: ignore[attr-defined]
    assert new_sid != "attacker-fixed"  # rotated (fixation defence)
    assert "attacker-fixed" not in store  # old id forgotten
    assert store[new_sid]["_user_id"] == 9  # persisted under the NEW id, not the old one
    assert isinstance(seen["user"], _User) and seen["user"].id == 9


@pytest.mark.asyncio
async def test_session_guard_user_id_reads_back_a_later_request() -> None:
    """Login on one request, then a *later* request over the same store reads the persisted id back
    (the read-half of login — what an app's session-based ``user_resolver`` calls)."""
    from arvel.http.middleware import StartSession

    store: dict[str, dict[str, Any]] = {}
    mw = StartSession(store=store, secure=False)
    req1 = _FakeSessionRequest()

    async def login(r: Any) -> str:
        await SessionGuard().login(_User(11), r)
        return "ok"

    token = current_user.set(None)
    try:
        await mw.handle(req1, login)
    finally:
        current_user.reset(token)
    sid_after_login = req1._session_id  # type: ignore[attr-defined]

    # a second, independent request presenting the rotated cookie
    req2 = _FakeSessionRequest({"session": sid_after_login})
    seen_uid: dict[str, Any] = {}

    async def read(r: Any) -> str:
        seen_uid["uid"] = await SessionGuard().user_id(r)
        return "ok"

    await mw.handle(req2, read)
    assert seen_uid["uid"] == 11


@pytest.mark.asyncio
async def test_session_guard_login_with_remember_issues_a_cookie() -> None:
    import sqlalchemy as sa

    from arvel.auth.remember import RememberToken, recall_remember_token
    from arvel.database import ConnectionResolver
    from arvel.http.middleware import StartSession

    db = ConnectionResolver()
    RememberToken.set_connection(db)
    await db.execute(sa.schema.CreateTable(RememberToken.__table__))
    try:
        mw = StartSession(store={}, secure=False)
        req = _FakeSessionRequest()

        async def dest(r: Any) -> str:
            await SessionGuard().login(_User(4), r, remember=True)
            return "ok"

        token = current_user.set(None)
        try:
            await mw.handle(req, dest)
        finally:
            current_user.reset(token)

        assert req._remember_set  # type: ignore[attr-defined]  # cookie flagged
        recalled = await recall_remember_token(req._remember_set)  # type: ignore[attr-defined]
        assert recalled is not None and recalled[0] == 4
    finally:
        await db.dispose()


@pytest.mark.asyncio
async def test_session_guard_logout_invalidates_clears_remember_and_current_user() -> None:
    import sqlalchemy as sa

    from arvel.auth.remember import (
        REMEMBER_COOKIE,
        RememberToken,
        issue_remember_token,
        recall_remember_token,
    )
    from arvel.database import ConnectionResolver
    from arvel.http.middleware import StartSession

    db = ConnectionResolver()
    RememberToken.set_connection(db)
    await db.execute(sa.schema.CreateTable(RememberToken.__table__))
    try:
        cookie = await issue_remember_token(5)
        store: dict[str, dict[str, Any]] = {"sid-1": {"_user_id": 5}}
        mw = StartSession(store=store, secure=False)
        req = _FakeSessionRequest({"session": "sid-1", REMEMBER_COOKIE: cookie})
        seen: dict[str, Any] = {}

        async def dest(r: Any) -> str:
            await SessionGuard().logout(r)
            seen["user"] = current_user.get()
            return "ok"

        token = current_user.set(_User(5))
        try:
            await mw.handle(req, dest)
        finally:
            current_user.reset(token)

        new_sid = req._session_id  # type: ignore[attr-defined]
        assert new_sid != "sid-1"  # rotated
        assert store[new_sid] == {}  # fresh empty session — old data (incl. _user_id) dropped
        assert seen["user"] is None  # current_user cleared
        assert req._remember_clear is True  # type: ignore[attr-defined]  # cookie flagged for clearing
        assert await recall_remember_token(cookie) is None  # remember token row deleted
    finally:
        await db.dispose()


# --- GuardManager -------------------------------------------------------------


def test_guard_manager_default_is_session() -> None:
    mgr = GuardManager()
    assert mgr.default_driver() == "session"
    assert isinstance(mgr.guard(), SessionGuard)


def test_guard_manager_resolves_local() -> None:
    assert isinstance(GuardManager().guard("local"), LocalGuard)


def test_guard_manager_extend() -> None:
    sentinel = object()
    mgr = GuardManager()
    mgr.extend("custom", lambda _app: sentinel)
    assert mgr.guard("custom") is sentinel


# --- AuthManager.attempt (recast through LocalGuard) ---------------------------


class _PwUser(Authenticatable):
    def __init__(self, uid: int, password_hash: str) -> None:
        self.id = uid
        self.password = password_hash

    def get_auth_password(self) -> Any:
        return self.password


@pytest.mark.asyncio
async def test_auth_manager_attempt_success() -> None:
    user = _PwUser(1, Hasher().make("hunter2"))

    async def provider(_credentials: dict[str, Any]) -> Any:
        return user

    mgr = AuthManager()
    ok = await mgr.attempt({"email": "ada", "password": "hunter2"}, provider)
    assert ok is True
    assert mgr.user() is user
    mgr.logout()


@pytest.mark.asyncio
async def test_auth_manager_attempt_wrong_password() -> None:
    user = _PwUser(1, Hasher().make("hunter2"))

    async def provider(_credentials: dict[str, Any]) -> Any:
        return user

    mgr = AuthManager()
    ok = await mgr.attempt({"email": "ada", "password": "nope"}, provider)
    assert ok is False
    assert mgr.guest()
