"""Auth (G7 hardening) — impersonation ("login as"), reversible + authorization-gated."""

from __future__ import annotations

from typing import Any

from arvel.auth import current_user
from arvel.auth.impersonation import (
    IMPERSONATOR_KEY,
    USER_KEY,
    impersonate,
    impersonator_id,
    is_impersonating,
    stop_impersonating,
)


class FakeUser:
    def __init__(self, uid: int, *, may_impersonate: bool = False) -> None:
        self.id = uid
        self._may = may_impersonate

    def get_auth_identifier(self) -> int:
        return self.id

    async def can(self, ability: str, *args: Any) -> bool:
        return self._may and ability == "impersonate"


class FakeRequest:
    def __init__(self, session: dict[str, Any] | None = None, sid: str = "sid-0") -> None:
        self.session = session if session is not None else {}
        self._session_id = sid


async def test_authorized_admin_can_impersonate() -> None:
    admin = FakeUser(1, may_impersonate=True)
    target = FakeUser(2)
    req = FakeRequest(sid="pre")
    token = current_user.set(admin)
    try:
        assert await impersonate(req, target) is True
        assert req.session[IMPERSONATOR_KEY] == 1  # real user stashed
        assert req.session[USER_KEY] == 2  # active user is the target
        assert req._session_id != "pre"  # session id rotated (identity switch)
        assert current_user.get() is target  # effective this request
        assert is_impersonating(req) is True
        assert impersonator_id(req) == 1
    finally:
        current_user.reset(token)


async def test_unauthorized_user_cannot_impersonate() -> None:
    nobody = FakeUser(1, may_impersonate=False)
    target = FakeUser(2)
    req = FakeRequest()
    token = current_user.set(nobody)
    try:
        assert await impersonate(req, target) is False  # fail closed
        assert IMPERSONATOR_KEY not in req.session
        assert USER_KEY not in req.session
        assert is_impersonating(req) is False
    finally:
        current_user.reset(token)


async def test_stop_returns_to_the_real_user() -> None:
    admin = FakeUser(1, may_impersonate=True)
    target = FakeUser(2)
    req = FakeRequest(sid="pre")
    token = current_user.set(admin)
    try:
        await impersonate(req, target)
        rotated = req._session_id
        assert await stop_impersonating(req) is True
        assert req.session[USER_KEY] == 1  # back to the admin
        assert IMPERSONATOR_KEY not in req.session  # marker cleared
        assert req._session_id != rotated  # rotated again on switch-back
        assert is_impersonating(req) is False
    finally:
        current_user.reset(token)


async def test_no_nesting() -> None:
    admin = FakeUser(1, may_impersonate=True)
    req = FakeRequest()
    token = current_user.set(admin)
    try:
        assert await impersonate(req, FakeUser(2)) is True
        # current_user is now the target (id 2, may_impersonate=False) — and we're already impersonating
        assert await impersonate(req, FakeUser(3)) is False  # no nesting / no escalation
        assert req.session[USER_KEY] == 2  # unchanged
    finally:
        current_user.reset(token)


async def test_no_self_impersonation() -> None:
    admin = FakeUser(1, may_impersonate=True)
    req = FakeRequest()
    token = current_user.set(admin)
    try:
        assert await impersonate(req, FakeUser(1)) is False  # can't impersonate yourself
    finally:
        current_user.reset(token)


async def test_stop_when_not_impersonating_is_false() -> None:
    req = FakeRequest()
    token = current_user.set(FakeUser(1))
    try:
        assert await stop_impersonating(req) is False
    finally:
        current_user.reset(token)


async def test_guest_cannot_impersonate() -> None:
    req = FakeRequest()
    token = current_user.set(None)  # no logged-in user
    try:
        assert await impersonate(req, FakeUser(2)) is False
    finally:
        current_user.reset(token)


async def test_target_none_and_no_session_fail_closed() -> None:
    admin = FakeUser(1, may_impersonate=True)
    token = current_user.set(admin)
    try:
        assert await impersonate(FakeRequest(), None) is False  # no target
        no_session = FakeRequest()
        no_session.session = None  # type: ignore[assignment]   # no StartSession ran
        assert await impersonate(no_session, FakeUser(2)) is False
    finally:
        current_user.reset(token)


class _FakeLog:
    """A stand-in for the framework Log facade root, recording (channel, level, event, fields)."""

    def __init__(self) -> None:
        self.records: list[tuple[str | None, str, str, dict[str, Any]]] = []
        self._channel: str | None = None

    def channel(self, name: str) -> _FakeLog:
        self._channel = name
        return self

    def info(self, event: str, **fields: Any) -> None:
        self.records.append((self._channel, "info", event, fields))

    def warning(self, event: str, **fields: Any) -> None:
        self.records.append((self._channel, "warning", event, fields))


async def test_audit_trail_records_start_stop_and_denied() -> None:
    from arvel.support.facades import Log

    admin = FakeUser(1, may_impersonate=True)
    nobody = FakeUser(5, may_impersonate=False)
    log = _FakeLog()
    Log.swap(log)
    try:
        req = FakeRequest()
        token = current_user.set(admin)
        try:
            await impersonate(req, FakeUser(2))
            await stop_impersonating(req)
        finally:
            current_user.reset(token)

        token = current_user.set(nobody)
        try:
            await impersonate(req, FakeUser(2))  # unauthorized → denied
        finally:
            current_user.reset(token)

        req2 = FakeRequest()
        token = current_user.set(admin)
        try:
            await impersonate(req2, FakeUser(2))  # now impersonating
            await impersonate(req2, FakeUser(3))  # nested → refused
        finally:
            current_user.reset(token)
    finally:
        Log.clear_swapped()

    by_event = {event: (channel, level, fields) for channel, level, event, fields in log.records}
    # every audit event goes to the `security` channel
    assert all(channel == "security" for channel, _l, _e, _f in log.records)
    assert by_event["auth.impersonation.started"][2]["impersonator_id"] == 1
    assert by_event["auth.impersonation.started"][2]["target_id"] == 2
    assert by_event["auth.impersonation.stopped"][2]["impersonator_id"] == 1
    # denied attempts log at warning, with a reason
    denied = [(lvl, f) for ch, lvl, e, f in log.records if e == "auth.impersonation.denied"]
    reasons = {f["reason"] for _lvl, f in denied}
    assert reasons == {"unauthorized", "already_impersonating"}
    assert all(lvl == "warning" for lvl, _f in denied)


async def test_audit_is_a_noop_without_an_app() -> None:
    """No app bound (and no Log swap) → _audit must not raise; impersonation still works."""
    admin = FakeUser(1, may_impersonate=True)
    req = FakeRequest()
    token = current_user.set(admin)
    try:
        assert await impersonate(req, FakeUser(2)) is True  # no crash despite no logger
    finally:
        current_user.reset(token)
