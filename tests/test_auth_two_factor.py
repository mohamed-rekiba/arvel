"""Auth (doc 15) — 2FA/TOTP on pyotp (mandated engine). Test-first."""

from __future__ import annotations

import contextlib
from typing import Any

import pytest

from arvel.auth.two_factor import (
    TwoFactor,
    TwoFactorRequired,
    begin_two_factor_challenge,
    complete_two_factor_challenge,
    confirm_two_factor,
    disable_two_factor,
    enable_two_factor,
    pending_two_factor_user_id,
    regenerate_recovery_codes,
    requires_two_factor_challenge,
    verify_two_factor,
)


def test_secret_then_verify_current_code() -> None:
    secret = TwoFactor.generate_secret()
    assert isinstance(secret, str) and len(secret) >= 16

    code = TwoFactor.current_code(secret)
    assert TwoFactor.verify(secret, code)  # the live code validates

    wrong = "000000" if code != "000000" else "111111"
    assert not TwoFactor.verify(secret, wrong)


def test_provisioning_uri_is_otpauth() -> None:
    uri = TwoFactor.provisioning_uri("JBSWY3DPEHPK3PXP", "ada@example.com", issuer="arvel")
    assert uri.startswith("otpauth://totp/")
    assert "issuer=arvel" in uri


def test_recovery_codes_are_unique() -> None:
    codes = TwoFactor.recovery_codes(8)
    assert len(codes) == 8
    assert len(set(codes)) == 8  # all distinct


# --- Fortify-style lifecycle: enable / confirm / verify / disable / regenerate -------------------


class _User:
    def __init__(self, uid: int = 1) -> None:
        self.id = uid
        self.email = "ada@example.com"
        self.two_factor_secret: str | None = None
        self.two_factor_recovery_codes: list[str] | None = None
        self.two_factor_confirmed_at: Any = None
        self.saved = 0

    async def save(self) -> None:
        self.saved += 1


async def test_enable_two_factor_stores_secret_and_hashed_codes_unconfirmed() -> None:
    user = _User()
    enrollment = await enable_two_factor(user)

    assert enrollment.provisioning_uri.startswith("otpauth://totp/")
    assert len(enrollment.recovery_codes) == 8

    assert user.two_factor_secret is not None
    assert user.two_factor_confirmed_at is None  # not confirmed by enabling alone
    assert user.two_factor_recovery_codes is not None
    # stored codes are hashed, not the plaintext shown to the user
    assert set(user.two_factor_recovery_codes).isdisjoint(enrollment.recovery_codes)
    assert user.saved == 1


async def test_confirm_two_factor_requires_a_live_totp_code() -> None:
    user = _User()
    await enable_two_factor(user)
    secret = user.two_factor_secret
    assert secret is not None

    assert await confirm_two_factor(user, "000000") is False
    assert user.two_factor_confirmed_at is None

    code = TwoFactor.current_code(secret)
    assert await confirm_two_factor(user, code) is True
    assert user.two_factor_confirmed_at is not None


async def test_disable_two_factor_clears_everything() -> None:
    user = _User()
    await enable_two_factor(user)
    await confirm_two_factor(user, TwoFactor.current_code(user.two_factor_secret))  # type: ignore[arg-type]

    await disable_two_factor(user)
    assert user.two_factor_secret is None
    assert user.two_factor_recovery_codes is None
    assert user.two_factor_confirmed_at is None


async def test_verify_two_factor_accepts_totp() -> None:
    user = _User()
    await enable_two_factor(user)
    code = TwoFactor.current_code(user.two_factor_secret)  # type: ignore[arg-type]
    assert await verify_two_factor(user, code) is True
    assert await verify_two_factor(user, "000000") is False


async def test_verify_two_factor_consumes_a_recovery_code_once() -> None:
    user = _User()
    enrollment = await enable_two_factor(user)
    recovery_code = enrollment.recovery_codes[0]

    assert await verify_two_factor(user, recovery_code) is True  # first use — accepted
    assert await verify_two_factor(user, recovery_code) is False  # single-use — now invalid
    assert len(user.two_factor_recovery_codes) == 7  # type: ignore[arg-type]


async def test_regenerate_recovery_codes_invalidates_the_old_set() -> None:
    user = _User()
    enrollment = await enable_two_factor(user)
    old_code = enrollment.recovery_codes[0]

    new_codes = await regenerate_recovery_codes(user)
    assert len(new_codes) == 8
    assert set(new_codes).isdisjoint(enrollment.recovery_codes)

    assert await verify_two_factor(user, old_code) is False  # old set is gone
    assert await verify_two_factor(user, new_codes[0]) is True  # new set works


# --- login-challenge state machine ----------------------------------------------------------


class _Request:
    def __init__(self) -> None:
        self.session: dict[str, Any] = {}


async def test_requires_two_factor_challenge_only_after_confirmation() -> None:
    user = _User()
    assert requires_two_factor_challenge(user) is False
    await enable_two_factor(user)
    assert requires_two_factor_challenge(user) is False  # enabled but not confirmed
    await confirm_two_factor(user, TwoFactor.current_code(user.two_factor_secret))  # type: ignore[arg-type]
    assert requires_two_factor_challenge(user) is True


def test_begin_two_factor_challenge_stashes_session_and_raises() -> None:
    request = _Request()
    user = _User(uid=42)
    with pytest.raises(TwoFactorRequired) as exc_info:
        begin_two_factor_challenge(request, user)
    assert exc_info.value.user_id == 42
    assert pending_two_factor_user_id(request) == 42


async def test_complete_two_factor_challenge_clears_pending_on_success() -> None:
    request = _Request()
    user = _User()
    await enable_two_factor(user)
    await confirm_two_factor(user, TwoFactor.current_code(user.two_factor_secret))  # type: ignore[arg-type]

    with contextlib.suppress(TwoFactorRequired):
        begin_two_factor_challenge(request, user)
    assert pending_two_factor_user_id(request) == user.id

    code = TwoFactor.current_code(user.two_factor_secret)  # type: ignore[arg-type]
    assert await complete_two_factor_challenge(request, user, code) is True
    assert pending_two_factor_user_id(request) is None  # cleared


async def test_complete_two_factor_challenge_leaves_pending_flag_on_failure() -> None:
    request = _Request()
    user = _User()
    await enable_two_factor(user)
    await confirm_two_factor(user, TwoFactor.current_code(user.two_factor_secret))  # type: ignore[arg-type]

    with contextlib.suppress(TwoFactorRequired):
        begin_two_factor_challenge(request, user)

    assert await complete_two_factor_challenge(request, user, "000000") is False
    assert pending_two_factor_user_id(request) == user.id  # retry still possible
