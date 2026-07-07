"""Email-verification signed tokens — email-hash binding (survives-email-change) + 60m TTL.

Password-reset moved to a stored broker (``arvel.auth.password_reset`` — see
``test_auth_password_reset.py``); the old stateless signed reset token is gone (A6)."""

from __future__ import annotations

from arvel.auth.flows import DEFAULT_TTL_SECONDS, email_verification_token, verify_email_token

SIG = "unit-test-signing-value"


def test_email_verification_roundtrip() -> None:
    token = email_verification_token(42, "ada@example.com", SIG)
    assert verify_email_token(token, "ada@example.com", SIG) == "42"


def test_bad_signature_rejected() -> None:
    token = email_verification_token(42, "ada@example.com", SIG)
    assert verify_email_token(token, "ada@example.com", "different-value") is None
    assert verify_email_token("not-a-token", "ada@example.com", SIG) is None


def test_email_change_invalidates_the_link() -> None:
    """A link generated for email A must fail once the user has changed to email B (audit finding:
    the old payload carried no email binding, so a stale link kept working after an email change)."""
    token = email_verification_token(7, "old@example.com", SIG)
    assert verify_email_token(token, "old@example.com", SIG) == "7"  # still the same email → valid
    assert verify_email_token(token, "new@example.com", SIG) is None  # changed → invalid


def test_email_normalisation_matches_case_and_whitespace_variants() -> None:
    token = email_verification_token(1, "Ada@Example.com", SIG)
    assert verify_email_token(token, " ada@example.com ", SIG) == "1"


def test_default_ttl_is_60_minutes() -> None:
    assert DEFAULT_TTL_SECONDS == 3600


def test_expired_token_rejected() -> None:
    token = email_verification_token(42, "ada@example.com", SIG)
    # max_age=-1: any elapsed age is "too old" — deterministic without manipulating the clock
    assert verify_email_token(token, "ada@example.com", SIG, max_age=-1) is None
