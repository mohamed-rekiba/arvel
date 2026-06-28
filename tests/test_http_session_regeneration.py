"""HTTP (G11 hardening) — session cookie issuance + id rotation / invalidation (fixation defence)."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.http.middleware import StartSession
from arvel.http.session import invalidate_session, regenerate_session


class FakeRequest:
    def __init__(self, session_id: str | None = None) -> None:
        self._sid = session_id
        self.session: dict[str, Any] | None = None

    def cookie(self, name: str, default: str | None = None) -> str | None:
        # name-agnostic: serves the one session cookie under whatever name is asked (session/__Host-)
        return self._sid if self._sid is not None else default


class FakeResponse:
    def __init__(self) -> None:
        self.cookies: list[tuple[str, str, dict[str, Any]]] = []

    def set_cookie(self, key: str, value: str, **kw: Any) -> None:
        self.cookies.append((key, value, kw))


# --- cookie issuance ----------------------------------------------------------


@pytest.mark.asyncio
async def test_new_session_issues_a_hardened_cookie() -> None:
    store: dict[str, dict[str, Any]] = {}
    mw = StartSession(store=store, secure=False)
    req = FakeRequest(session_id=None)  # client has no session cookie yet

    async def dest(r: Any) -> str:
        r.session["k"] = "v"
        return "ok"

    await mw.handle(req, dest)
    sid = req._session_id  # type: ignore[attr-defined]
    assert store[sid] == {"k": "v"}

    resp = FakeResponse()
    await mw.terminate(req, resp)
    assert len(resp.cookies) == 1
    key, value, kw = resp.cookies[0]
    assert (key, value) == ("session", sid)
    assert kw["httponly"] is True and kw["samesite"] == "lax" and kw["secure"] is False


@pytest.mark.asyncio
async def test_secure_flag_defaults_on() -> None:
    mw = StartSession(store={})  # secure defaults True
    req = FakeRequest(session_id=None)

    async def dest(_r: Any) -> str:
        return "ok"

    await mw.handle(req, dest)
    resp = FakeResponse()
    await mw.terminate(req, resp)
    assert resp.cookies[0][2]["secure"] is True


@pytest.mark.asyncio
async def test_existing_session_without_rotation_sets_no_cookie() -> None:
    store: dict[str, dict[str, Any]] = {"abc": {"user_id": 7}}
    mw = StartSession(store=store, secure=False)
    req = FakeRequest(session_id="abc")

    async def dest(_r: Any) -> str:
        return "ok"

    await mw.handle(req, dest)
    resp = FakeResponse()
    await mw.terminate(req, resp)
    assert resp.cookies == []  # had a valid cookie, nothing rotated → no Set-Cookie
    assert store["abc"] == {"user_id": 7}


# --- regeneration (anti session-fixation) -------------------------------------


@pytest.mark.asyncio
async def test_regenerate_rotates_id_preserves_data_and_drops_old() -> None:
    store: dict[str, dict[str, Any]] = {"attacker-fixed": {"cart": [1]}}
    mw = StartSession(store=store, secure=False)
    req = FakeRequest(session_id="attacker-fixed")

    async def dest(r: Any) -> str:
        r.session["user_id"] = 7  # the user logs in
        regenerate_session(r)  # rotate the (possibly fixed) id
        return "ok"

    await mw.handle(req, dest)
    new_sid = req._session_id  # type: ignore[attr-defined]
    assert new_sid != "attacker-fixed"
    assert "attacker-fixed" not in store  # old id forgotten
    assert store[new_sid] == {"cart": [1], "user_id": 7}  # data carried to the new id

    resp = FakeResponse()
    await mw.terminate(req, resp)
    assert resp.cookies[0][1] == new_sid  # new cookie issued


@pytest.mark.asyncio
async def test_invalidate_clears_data_and_drops_old() -> None:
    store: dict[str, dict[str, Any]] = {"sid1": {"user_id": 7}}
    mw = StartSession(store=store, secure=False)
    req = FakeRequest(session_id="sid1")

    async def dest(r: Any) -> str:
        invalidate_session(r)  # logout
        return "ok"

    await mw.handle(req, dest)
    new_sid = req._session_id  # type: ignore[attr-defined]
    assert new_sid != "sid1"
    assert "sid1" not in store
    assert store[new_sid] == {}  # fresh empty session

    resp = FakeResponse()
    await mw.terminate(req, resp)
    assert resp.cookies[0][1] == new_sid


# --- __Host- cookie prefix (L2 hardening) -------------------------------------


@pytest.mark.asyncio
async def test_host_prefix_cookie_name_when_secure() -> None:
    mw = StartSession(store={})  # secure defaults True → __Host- on
    req = FakeRequest(session_id=None)

    async def dest(_r: Any) -> str:
        return "ok"

    await mw.handle(req, dest)
    resp = FakeResponse()
    await mw.terminate(req, resp)
    assert resp.cookies[0][0] == "__Host-session"  # prefixed name issued


@pytest.mark.asyncio
async def test_plain_cookie_name_when_not_secure() -> None:
    mw = StartSession(
        store={}, secure=False
    )  # dev http → __Host- rejected by browsers → plain name
    req = FakeRequest(session_id=None)

    async def dest(_r: Any) -> str:
        return "ok"

    await mw.handle(req, dest)
    resp = FakeResponse()
    await mw.terminate(req, resp)
    assert resp.cookies[0][0] == "session"


@pytest.mark.asyncio
async def test_host_prefix_can_be_opted_out_while_secure() -> None:
    mw = StartSession(store={}, secure=True, host_prefix=False)
    req = FakeRequest(session_id=None)

    async def dest(_r: Any) -> str:
        return "ok"

    await mw.handle(req, dest)
    resp = FakeResponse()
    await mw.terminate(req, resp)
    assert resp.cookies[0][0] == "session"  # explicit opt-out → plain name (still Secure)
    assert resp.cookies[0][2]["secure"] is True


@pytest.mark.asyncio
async def test_prefixed_sid_is_read_back_and_session_loads() -> None:
    store: dict[str, dict[str, Any]] = {"abc": {"user_id": 7}}
    mw = StartSession(store=store)  # secure → reads __Host-session; the double serves it
    req = FakeRequest(session_id="abc")
    seen: dict[str, Any] = {}

    async def dest(r: Any) -> str:
        seen.update(r.session)
        return "ok"

    await mw.handle(req, dest)
    assert seen == {"user_id": 7}  # existing session loaded via the prefixed cookie
    resp = FakeResponse()
    await mw.terminate(req, resp)
    assert resp.cookies == []  # had a valid cookie, nothing rotated → no Set-Cookie


# --- cookie emission is success-path only (documented; fail-closed server-side) ---


@pytest.mark.asyncio
async def test_handler_error_still_forgets_old_session_id_server_side() -> None:
    """If the handler raises after a regenerate, terminate (cookie emit) is skipped — but handle's
    teardown has already forgotten the old id and saved the new one, so no live old id survives."""
    store: dict[str, dict[str, Any]] = {"attacker-fixed": {"cart": [1]}}
    mw = StartSession(store=store, secure=False)
    req = FakeRequest(session_id="attacker-fixed")

    async def dest(r: Any) -> str:
        r.session["user_id"] = 7
        regenerate_session(r)
        raise RuntimeError("boom after rotation")

    with pytest.raises(RuntimeError):
        await mw.handle(req, dest)
    new_sid = req._session_id  # type: ignore[attr-defined]
    assert "attacker-fixed" not in store  # old id forgotten despite the error (fail-closed)
    assert store[new_sid] == {"cart": [1], "user_id": 7}  # rotation persisted server-side
