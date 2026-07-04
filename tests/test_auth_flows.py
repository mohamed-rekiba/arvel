"""Email-verification + password-reset signed tokens."""

from __future__ import annotations

from arvel.auth.flows import (
    email_verification_token,
    password_reset_token,
    verify_email_token,
    verify_password_reset_token,
)

SIG = "unit-test-signing-value"


def test_email_verification_roundtrip() -> None:
    token = email_verification_token(42, SIG)
    assert verify_email_token(token, SIG) == 42


def test_password_reset_roundtrip() -> None:
    token = password_reset_token(7, SIG)
    assert verify_password_reset_token(token, SIG) == 7


def test_bad_signature_rejected() -> None:
    token = email_verification_token(42, SIG)
    assert verify_email_token(token, "different-value") is None
    assert verify_email_token("not-a-token", SIG) is None


def test_token_purposes_do_not_cross() -> None:
    # a verification token must not be accepted as a password-reset token (and vice versa)
    verify = email_verification_token(1, SIG)
    reset = password_reset_token(1, SIG)
    assert verify_password_reset_token(verify, SIG) is None
    assert verify_email_token(reset, SIG) is None
