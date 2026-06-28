"""Auth (L1b) — centralized auth.* configuration: components read config-sourced defaults.

Precedence everywhere: explicit constructor arg > auth.* config > built-in default; with no app
bound, the built-in default applies (so test-constructed components keep working)."""

from __future__ import annotations

from typing import Any

from arvel.auth.confirm import confirm_password, password_confirmed
from arvel.auth.impersonation import impersonate
from arvel.auth.remember import DEFAULT_TTL, RememberMe
from arvel.auth.throttle import LoginRateLimiter
from arvel.dates import Date
from arvel.http.middleware import StartSession
from arvel.kernel.config import Repository
from arvel.kernel.globals import set_application
from arvel.security import Hasher

from arvel.auth import current_user  # isort: skip


class _FakeApp:
    def __init__(self, config_items: dict[str, Any]) -> None:
        self._config = Repository(config_items)

    def make(self, key: str) -> Any:
        if key == "config":
            return self._config
        raise KeyError(key)


# --- session ------------------------------------------------------------------


def test_session_reads_config_and_arg_wins() -> None:
    set_application(_FakeApp({"session": {"secure": False, "lifetime": 111}}))
    try:
        mw = StartSession()
        # lifetime is MINUTES (DR-0019); _max_age is the seconds value (x60) for cookie/TTL.
        assert mw._secure is False and mw._max_age == 111 * 60  # from config
        assert StartSession(secure=True, lifetime=222)._secure is True  # explicit arg wins
    finally:
        set_application(None)
    # no app → defaults: 120 min → 7200s
    assert StartSession()._secure is True and StartSession()._max_age == 7200


def test_explicit_falsy_arg_overrides_truthy_config() -> None:
    """The sentinel is `is not None`, not truthiness — an intentional False/0 must win over config."""
    set_application(
        _FakeApp({"session": {"secure": True}, "auth": {"lockout": {"fail_open": True}}})
    )
    try:
        assert StartSession(secure=False)._secure is False  # not swallowed by the truthy config
        assert LoginRateLimiter(cache=None, fail_open=False)._fail_open is False
    finally:
        set_application(None)


# --- lockout ------------------------------------------------------------------


def test_lockout_reads_config() -> None:
    set_application(
        _FakeApp(
            {"auth": {"lockout": {"max_attempts": 9, "decay_seconds": 60, "fail_open": False}}}
        )
    )
    try:
        lim = LoginRateLimiter(cache=None)
        assert lim.max_attempts == 9 and lim.decay_seconds == 60 and lim._fail_open is False
        assert LoginRateLimiter(cache=None, max_attempts=3).max_attempts == 3  # arg wins
    finally:
        set_application(None)
    assert LoginRateLimiter(cache=None).max_attempts == 5  # no app → default


# --- remember-me --------------------------------------------------------------


def test_remember_reads_config() -> None:
    set_application(_FakeApp({"auth": {"remember": {"secure": False, "ttl": 123}}}))
    try:
        mw = RememberMe(lambda uid: None)
        assert mw._secure is False and mw._ttl == 123
    finally:
        set_application(None)
    mw2 = RememberMe(lambda uid: None)
    assert mw2._secure is True and mw2._ttl == DEFAULT_TTL  # no app → defaults


# --- impersonation ability ----------------------------------------------------


class _Admin:
    id = 1

    def get_auth_identifier(self) -> int:
        return self.id

    async def can(self, ability: str, *args: Any) -> bool:
        return ability == "su"  # only the custom ability name grants it


class _Req:
    def __init__(self) -> None:
        self.session: dict[str, Any] = {}
        self._session_id = "sid"


async def test_impersonation_ability_name_from_config() -> None:
    req = _Req()
    token = current_user.set(_Admin())
    try:
        # no app → default ability "impersonate" → _Admin.can returns False
        assert await impersonate(req, _Admin.__new__(_Admin)) is False
        set_application(_FakeApp({"auth": {"impersonation": {"ability": "su"}}}))
        target = _Admin.__new__(_Admin)
        target.id = 2  # type: ignore[misc]
        assert await impersonate(req, target) is True  # config ability "su" → allowed
    finally:
        set_application(None)
        current_user.reset(token)


# --- password-confirm window --------------------------------------------------


class _CUser:
    id = 1

    def get_auth_identifier(self) -> int:
        return self.id

    def get_auth_password(self) -> str:
        return Hasher().make("secret")


async def test_password_timeout_window_from_config() -> None:
    base = Date.now()
    Date.set_test_now(base)
    token = current_user.set(_CUser())
    set_application(_FakeApp({"auth": {"password_timeout": 300}}))
    try:
        req = _Req()
        await confirm_password(req, "secret")
        assert password_confirmed(req) is True  # within the configured 300s
        Date.set_test_now(base.add(seconds=360))
        assert password_confirmed(req) is False  # past the configured window
    finally:
        set_application(None)
        current_user.reset(token)
        Date.set_test_now(None)
