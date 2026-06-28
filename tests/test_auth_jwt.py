"""Auth (doc 15) — JWT on pyjwt (mandated engine). Test-first."""

from __future__ import annotations

from arvel.auth.jwt_guard import Jwt

SIG = "unit-test-signing-value-padded-past-32-bytes"


def test_encode_decode_roundtrip() -> None:
    token = Jwt.encode({"sub": "42", "role": "admin"}, SIG)
    claims = Jwt.decode(token, SIG)
    assert claims is not None
    assert claims["sub"] == "42"
    assert claims["role"] == "admin"


def test_wrong_secret_returns_none() -> None:
    token = Jwt.encode({"sub": "1"}, SIG)
    assert Jwt.decode(token, "a-totally-different-secret-of-ample-length") is None


def test_expired_token_returns_none() -> None:
    token = Jwt.encode({"sub": "1"}, SIG, ttl=-1)  # exp in the past
    assert Jwt.decode(token, SIG) is None


def test_tampered_token_returns_none() -> None:
    assert Jwt.decode("not.a.valid-token", SIG) is None
