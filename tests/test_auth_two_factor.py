"""Auth (doc 15) — 2FA/TOTP on pyotp (mandated engine). Test-first."""

from __future__ import annotations

from arvel.auth.two_factor import TwoFactor


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
